"""Reliable OpenWA group broadcasts for ordinary tournament milestones."""
import json
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import current_app

from database import CupQualification, TournamentBroadcast, TournamentPrizePool, User, db


ORDINARY_TYPES = {'standard', 'premium', 'deluxe'}
MAX_ATTEMPTS = 5


def _enabled():
    return bool(
        current_app.config.get('OPENWA_TOURNAMENT_BROADCASTS_ENABLED')
        and current_app.config.get('OPENWA_BROADCAST_GROUP_ID')
    )


def _amount(amount, pilot):
    value = f'{float(amount or 0):.2f}'.rstrip('0').rstrip('.')
    return f'{value} credits' if pilot else f'E{value}'


def _group_id():
    value = str(current_app.config.get('OPENWA_BROADCAST_GROUP_ID') or '').strip()
    return value if value.endswith('@g.us') else f'{value}@g.us'


def _queue(tournament, event_type, message):
    if not _enabled() or tournament.tournament_type not in ORDINARY_TYPES:
        return None
    key = f'tournament:{tournament.id}:{event_type}'
    existing = TournamentBroadcast.query.filter_by(event_key=key).first()
    if existing is not None:
        return existing
    row = TournamentBroadcast(
        tournament_id=tournament.id, event_type=event_type, event_key=key,
        message_body=message, status='pending', next_attempt_at=datetime.utcnow(),
    )
    db.session.add(row)
    return row


def queue_tournament_created(tournament, creator_username):
    """Queue a public announcement only after tournament creation commits."""
    pilot = bool(current_app.config.get('PILOT_MODE'))
    lines = [
        f'🏆 {tournament.tournament_name} Open',
        '',
        f'{tournament.max_players}-player bracket hosted by {creator_username}.',
        f'Entry: {_amount(tournament.entry_fee, pilot)}',
    ]
    public_url = str(current_app.config.get('PUBLIC_APP_URL') or '').strip()
    if public_url:
        lines.append(f'Join now: {public_url}/tournaments/{tournament.id}/bracket')
    if pilot and current_app.config.get('CUP_QUALIFICATION_ENABLED'):
        lines.extend(['', 'Winner qualifies to contest in the upcoming uMshova Cup Tournament.'])
    return _queue(tournament, 'created', '\n'.join(lines))


def queue_tournament_results(tournament):
    """Queue settled podium results. Internal fees are never included."""
    if tournament.status != 'completed':
        return None
    pilot = bool(current_app.config.get('PILOT_MODE'))
    prize_rows = {
        row.placement: row.prize_amount
        for row in TournamentPrizePool.query.filter_by(tournament_id=tournament.id).all()
    }
    qualification = CupQualification.query.filter_by(
        source_tournament_id=tournament.id
    ).first()
    placements = ((1, tournament.winner_id), (2, tournament.runner_up_id), (3, tournament.third_place_id))
    labels = {1: '1st', 2: '2nd', 3: '3rd'}
    lines = [f'🏆 {tournament.tournament_name} Results', '']
    for placement, user_id in placements:
        if not user_id:
            continue
        user = db.session.get(User, user_id)
        if not user:
            continue
        suffix = ' (Qualified)' if (
            placement == 1 and qualification is not None
            and qualification.status in {'qualified', 'checked_in'}
        ) else ''
        lines.append(f'{labels[placement]}: {user.username} — {_amount(prize_rows.get(placement), pilot)}{suffix}')
    lines.extend(['', 'Congratulations to all players!'])
    return _queue(tournament, 'results', '\n'.join(lines))


def _deliver(row):
    base = str(current_app.config.get('OPENWA_API_URL') or '').strip().replace('\\:', ':').replace('\\/', '/').rstrip('/\\')
    session_id = str(current_app.config.get('OPENWA_SESSION_ID') or '').strip()
    key = str(current_app.config.get('OPENWA_API_KEY') or '').strip()
    parsed = urlsplit(base)
    if not base or not session_id or not key or parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise RuntimeError('OpenWA broadcast configuration is incomplete')
    request = Request(
        base + '/api/sessions/' + quote(session_id, safe='') + '/messages/send-text',
        data=json.dumps({'chatId': _group_id(), 'text': row.message_body}).encode(),
        headers={'Content-Type': 'application/json', 'X-API-Key': key}, method='POST',
    )
    with urlopen(request, timeout=float(current_app.config.get('OPENWA_TIMEOUT', 10))) as response:
        body = json.loads(response.read().decode() or '{}')
    return body.get('messageId')


def process_tournament_broadcasts(limit=10):
    """Deliver due outbox rows; errors are retried without replaying sent rows."""
    if not _enabled():
        return 0
    now = datetime.utcnow()
    rows = TournamentBroadcast.query.filter(
        TournamentBroadcast.status.in_(('pending', 'retry')),
        (TournamentBroadcast.next_attempt_at.is_(None)) | (TournamentBroadcast.next_attempt_at <= now),
    ).order_by(TournamentBroadcast.created_at).limit(limit).all()
    sent = 0
    for row in rows:
        row.attempt_count += 1
        try:
            row.openwa_message_id = _deliver(row)
            row.status = 'sent'
            row.sent_at = datetime.utcnow()
            row.last_error = None
            sent += 1
        except (HTTPError, URLError, ValueError, OSError, RuntimeError) as exc:
            row.last_error = type(exc).__name__
            if row.attempt_count >= MAX_ATTEMPTS:
                row.status = 'failed'
                row.next_attempt_at = None
            else:
                row.status = 'retry'
                row.next_attempt_at = datetime.utcnow() + timedelta(minutes=2 ** row.attempt_count)
            current_app.logger.warning('Tournament broadcast delivery failed event=%s error=%s', row.event_key, row.last_error)
        db.session.commit()
    return sent
