"""Durable WhatsApp delivery for direct wallet-credit notifications."""
import json
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


def _format_credits(amount):
    return f'{float(amount):.2f}'.rstrip('0').rstrip('.')


def queue_admin_credit_award(user_id, wallet_adjustment_id, amount):
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

    event_key = f'wallet-credit-award:{int(wallet_adjustment_id)}'
    existing = WalletNotification.query.filter_by(event_key=event_key).first()
    if existing is not None:
        return existing
    credit_amount = _format_credits(amount)
    message = (
        f'🎉 You have been awarded {credit_amount} uMshova credits!\n\n'
        'Your credits are ready to use in a tournament. Create or join a bracket here:\n'
        f'{_public_tournaments_url()}\n\n'
        'Good luck and enjoy the game!'
    )
    row = WalletNotification(
        user_id=user.id,
        wallet_adjustment_id=int(wallet_adjustment_id),
        event_type='admin_credit_award',
        event_key=event_key,
        recipient_chat_id=chat_id,
        message_body=message,
        status='pending',
        next_attempt_at=datetime.utcnow(),
    )
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
        body = json.loads(response.read().decode() or '{}')
    return body.get('messageId')


def process_wallet_notifications(limit=10):
    """Deliver queued wallet notifications without blocking admin requests."""
    if not _enabled():
        return 0
    now = datetime.utcnow()
    sent = 0
    for _ in range(limit):
        row = WalletNotification.query.filter(
            WalletNotification.status.in_(('pending', 'retry', 'sending')),
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
            if row.attempt_count >= MAX_ATTEMPTS:
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
