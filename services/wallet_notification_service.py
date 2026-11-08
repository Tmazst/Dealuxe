"""Durable WhatsApp delivery for direct wallet-credit notifications."""
import json
import socket
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import current_app

from database import User, WalletNotification, db
from services.contact_validator import ContactValidationError, ContactValidator


MAX_ATTEMPTS = 5


def _enabled():
    return bool(current_app.config.get('OPENWA_WALLET_NOTIFICATIONS_ENABLED'))


def _public_tournaments_url():
    base = str(current_app.config.get('PUBLIC_APP_URL') or '').strip().rstrip('/')
    return f'{base}/#tournaments' if base else '/tournaments'


def _membership_invitation():
    form_url = str(current_app.config.get('UMSHOVA_MEMBERSHIP_FORM_URL') or '').strip()
    if not form_url:
        return ''
    return (
        '\n\nAre you interested in becoming a uMshova member?\n'
        'Register for uMshova membership here:\n'
        f'{form_url}'
    )


def _welcome_group_invitation():
    """Return the optional community invite for first-time registrants only."""
    invite_url = str(
        current_app.config.get('UMSHOVA_WHATSAPP_GROUP_INVITE_URL') or ''
    ).strip()
    if not invite_url:
        return ''
    return (
        '\n\nJoin the uMshova WhatsApp community for tournament updates and news:\n'
        f'{invite_url}'
    )


def _format_credits(amount):
    return f'{float(amount):.2f}'.rstrip('0').rstrip('.')


def _build_credit_message(amount, welcome=False):
    """Build the two public wallet notification variants without delivery IO."""
    credit_amount = _format_credits(amount)
    opening = (
        f'🎉 Welcome to uMshova! You have received {credit_amount} credits!'
        if welcome else f'🎉 You have been awarded {credit_amount} uMshova credits!'
    )
    return (
        f'{opening}\n\n'
        'Your credits are ready to use in a tournament. Create or join a bracket here:\n'
        f'{_public_tournaments_url()}\n\n'
        'Good luck and enjoy the game!'
        f'{_welcome_group_invitation() if welcome else _membership_invitation()}'
    )


def _queue_credit_notification(
    user_id, event_type, event_key, amount, *, wallet_adjustment_id=None,
    transaction_id=None, welcome=False,
):
    """Add one notification to the current transaction, if delivery is enabled.

    Missing or invalid phones never prevent an administrator from awarding the
    credits. They are recorded in the application log so the account can be
    corrected before the next award.
    """
    if not _enabled():
        return None
    user = db.session.get(User, int(user_id))
    if user is None or not user.phone:
        current_app.logger.warning(
            'Wallet notification not queued: user_id=%s has no registered phone', user_id
        )
        return None
    try:
        chat_id = ContactValidator.to_openwa_chat_id(user.phone, user.country)
    except ContactValidationError:
        current_app.logger.warning(
            'Wallet notification not queued: user_id=%s has an invalid phone', user_id
        )
        return None

    existing = WalletNotification.query.filter_by(event_key=event_key).first()
    if existing is not None:
        return existing
    message = _build_credit_message(amount, welcome=welcome)
    row = WalletNotification(
        user_id=user.id,
        wallet_adjustment_id=wallet_adjustment_id,
        transaction_id=transaction_id,
        event_type=event_type,
        event_key=event_key,
        recipient_chat_id=chat_id,
        message_body=message,
        status='pending',
        next_attempt_at=datetime.utcnow(),
    )
    db.session.add(row)
    return row


def queue_admin_credit_award(user_id, wallet_adjustment_id, amount):
    """Queue a notification for one positive admin credit award."""
    return _queue_credit_notification(
        user_id,
        'admin_credit_award',
        f'wallet-credit-award:{int(wallet_adjustment_id)}',
        amount,
        wallet_adjustment_id=int(wallet_adjustment_id),
    )


def queue_registration_credit(user_id, transaction_id, amount):
    """Queue the one-time welcome credit message after verified registration."""
    return _queue_credit_notification(
        user_id,
        'registration_credit',
        f'registration-credit:{int(transaction_id)}',
        amount,
        transaction_id=int(transaction_id),
        welcome=True,
    )


def queue_offline_match_start(tournament, room, starter_id, socketio):
    """Queue one direct alert per match, using authenticated socket presence."""
    if not _enabled() or starter_id not in (room.player1_id, room.player2_id) or socketio is None:
        return None
    opponent_id = room.player2_id if starter_id == room.player1_id else room.player1_id
    # A user can have several tabs/devices. Any authenticated socket counts.
    if any(socketio.server.manager.get_participants('/', f'user_{opponent_id}')):
        return None
    user = db.session.get(User, opponent_id)
    starter = db.session.get(User, starter_id)
    if user is None or starter is None or not user.phone:
        return None
    try:
        chat_id = ContactValidator.to_openwa_chat_id(user.phone, user.country)
    except ContactValidationError:
        current_app.logger.warning('Match alert skipped: invalid phone for user_id=%s', opponent_id)
        return None
    key = f'match-start:{room.match_id}:user:{opponent_id}'
    existing = WalletNotification.query.filter_by(event_key=key).first()
    if existing is not None:
        return existing
    minutes = room.turn_duration_seconds // 60
    base = str(current_app.config.get('PUBLIC_APP_URL') or '').strip().rstrip('/')
    message = (
        f'Your opponent {starter.username} has started your match in {tournament.tournament_name}.\n\n'
        f'Time per turn: {minutes} minutes. If you miss your turn, the opportunity passes '
        'without cards being played. If you do not defend, your opponent '
        'can attack again and may win when their hand meets the winning conditions.\n\n'
        f'Join your match: {base}/game/{room.room_code}'
    )
    row = WalletNotification(user_id=opponent_id, event_type='offline_match_start',
                             event_key=key, recipient_chat_id=chat_id,
                             message_body=message, status='pending',
                             next_attempt_at=datetime.utcnow())
    db.session.add(row)
    return row


def _deliver(row):
    base = str(current_app.config.get('OPENWA_API_URL') or '').strip()
    base = base.replace('\\:', ':').replace('\\/', '/').rstrip('/\\')
    session_id = str(current_app.config.get('OPENWA_SESSION_ID') or '').strip()
    api_key = str(current_app.config.get('OPENWA_API_KEY') or '').strip()
    parsed = urlsplit(base)
    if not base or not session_id or not api_key or parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise RuntimeError('OpenWA wallet notification configuration is incomplete')
    request = Request(
        base + '/api/sessions/' + quote(session_id, safe='') + '/messages/send-text',
        data=json.dumps({'chatId': row.recipient_chat_id, 'text': row.message_body}).encode(),
        headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
        method='POST',
    )
    with urlopen(request, timeout=float(current_app.config.get('OPENWA_TIMEOUT', 10))) as response:
        raw_body = response.read().decode(errors='replace')
    try:
        body = json.loads(raw_body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    message_id = body.get('messageId') if isinstance(body, dict) else None
    return str(message_id) if message_id is not None else None


def _is_delivery_timeout(exc):
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    return isinstance(exc, URLError) and isinstance(
        getattr(exc, 'reason', None), (TimeoutError, socket.timeout)
    )


def process_wallet_notifications(limit=10):
    """Deliver queued wallet notifications without blocking admin requests."""
    if not _enabled():
        return 0
    now = datetime.utcnow()
    sent = 0
    for _ in range(limit):
        row = WalletNotification.query.filter(
            WalletNotification.status.in_(('pending', 'retry')),
            (WalletNotification.next_attempt_at.is_(None))
            | (WalletNotification.next_attempt_at <= now),
        ).order_by(WalletNotification.created_at).with_for_update(skip_locked=True).first()
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
                row.status = 'delivery_unknown'
                row.next_attempt_at = None
            elif row.attempt_count >= MAX_ATTEMPTS:
                row.status = 'failed'
                row.next_attempt_at = None
            else:
                row.status = 'retry'
                row.next_attempt_at = datetime.utcnow() + timedelta(minutes=2 ** row.attempt_count)
            current_app.logger.warning(
                'Wallet notification delivery failed event=%s error=%s',
                row.event_key, row.last_error,
            )
        db.session.commit()
    return sent
