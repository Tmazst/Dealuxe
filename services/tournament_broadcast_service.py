"""Reliable OpenWA group broadcasts for ordinary tournament milestones."""
import json
import socket
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
        f'🏆 New Tournament Created: {tournament.tournament_name}',
        '',
        f' Status: Open',
        f'{tournament.max_players}-player bracket hosted by: {creator_username}.',
        f'Entry: {_amount(tournament.entry_fee, pilot)}',
    ]
    if tournament.is_promotional:
        lines[0] = f'{tournament.tournament_name} - PROMOTIONAL TOURNAMENT'
        lines.extend(['No qualification required.', 'Host does not play.'])
        if not tournament.promotional_wallet_payouts:
            lines.append('Win E25 Data bonus.')
        schedule = tournament.schedule
        if schedule and schedule.scheduled_start_at:
            start = schedule.scheduled_start_at + timedelta(hours=2)
            lines.append(f'Start Time: {start:%d %B %Y at %H:%M} SAST.')
    public_url = str(current_app.config.get('PUBLIC_APP_URL') or '').strip()
    if public_url:
        lines.append(f'Play now: {public_url}/#tournaments')
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
    label = 'PROMOTIONAL TOURNAMENT — ' if tournament.is_promotional else ''
    lines = [f'🏆 {label}{tournament.tournament_name} Results', '']
    if tournament.is_promotional and not tournament.promotional_wallet_payouts:
        lines.append('Results only.')
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
        # A 2xx HTTP status means OpenWA accepted the message. Some OpenWA
        # releases return an empty/non-JSON body or use a different message-id
        # field, neither of which must cause a successful broadcast to repeat.
        raw_body = response.read().decode(errors='replace')
    try:
        body = json.loads(raw_body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    message_id = body.get('messageId') if isinstance(body, dict) else None
    return str(message_id) if message_id is not None else None


def _is_delivery_timeout(exc):
    """A timeout may occur after OpenWA has already accepted the message."""
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    return isinstance(exc, URLError) and isinstance(
        getattr(exc, 'reason', None), (TimeoutError, socket.timeout)
    )


def process_tournament_broadcasts(limit=10):
    """Deliver due outbox rows; errors are retried without replaying sent rows."""
    if not _enabled():
        return 0
    now = datetime.utcnow()
    sent = 0
    for _ in range(limit):
        # Claim one message before contacting OpenWA. A worker crash after the
        # provider accepts the request is delivery-ambiguous: resending would
        # spam the group. Therefore only explicit pending/retry events are sent
        # automatically; a stranded ``sending`` row is visible for review.
        row = TournamentBroadcast.query.filter(
            TournamentBroadcast.status.in_(('pending', 'retry')),
            (TournamentBroadcast.next_attempt_at.is_(None)) | (TournamentBroadcast.next_attempt_at <= now),
        ).order_by(TournamentBroadcast.created_at).with_for_update(skip_locked=True).first()
        if row is None:
            break
        row.status = 'sending'
        row.next_attempt_at = now + timedelta(minutes=5)
        row.attempt_count += 1
        db.session.commit()
        try:
            row.openwa_message_id = _deliver(row)
            row.status = 'sent'
            row.sent_at = datetime.utcnow()
            row.last_error = None
            row.next_attempt_at = None
            sent += 1
        except (HTTPError, URLError, ValueError, OSError, RuntimeError) as exc:
            row.last_error = type(exc).__name__
            if _is_delivery_timeout(exc):
                # Do not risk posting the same announcement again. This row is
                # retained for an operator to review, rather than retried.
                row.status = 'delivery_unknown'
                row.next_attempt_at = None
            elif row.attempt_count >= MAX_ATTEMPTS:
                row.status = 'failed'
                row.next_attempt_at = None
            else:
                row.status = 'retry'
                row.next_attempt_at = datetime.utcnow() + timedelta(minutes=2 ** row.attempt_count)
            current_app.logger.warning('Tournament broadcast delivery failed event=%s error=%s', row.event_key, row.last_error)
        db.session.commit()
    return sent
