"""One-time registration verification with email and OpenWA delivery."""
import hashlib
import hmac
import json
import secrets
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import current_app

from database import RegistrationVerification, db
from services.contact_validator import ContactValidator


CODE_LIFETIME = timedelta(minutes=5)
RESEND_DELAY = timedelta(seconds=60)
MAX_ATTEMPTS = 5
MAX_RESENDS = 3


class RegistrationSetupError(RuntimeError):
    """Safe, user-displayable registration setup failure category."""

    def __init__(self, code, user_message, *, provider_status=None):
        super().__init__(code)
        self.code = code
        self.user_message = user_message
        self.provider_status = provider_status


def _digest(value):
    return hmac.new(
        current_app.secret_key.encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def _setting(key, default=''):
    return str(current_app.config.get(key, default) or '').strip()


def _send_email(address, code):
    host = _setting('SMTP_HOST')
    if not host or not _setting('SMTP_FROM'):
        raise RegistrationSetupError(
            'email_not_configured',
            'Email verification is not set up yet. Please choose WhatsApp or contact support.',
        )
    message = EmailMessage()
    message['Subject'] = 'Your Dealuxe verification code'
    message['From'] = _setting('SMTP_FROM')
    message['To'] = address
    message.set_content(
        f'Your Dealuxe registration code is {code}. It expires in 5 minutes. '
        'If you did not request this, you can ignore this message.'
    )
    try:
        port = int(_setting('SMTP_PORT', '587'))
        timeout = float(_setting('SMTP_TIMEOUT', '10'))
        use_ssl = _setting('SMTP_USE_SSL').lower() in {'1', 'true', 'yes'}
        if use_ssl:
            client = smtplib.SMTP_SSL(
                host, port, timeout=timeout, context=ssl.create_default_context()
            )
        else:
            client = smtplib.SMTP(host, port, timeout=timeout)
        with client:
            if _setting('SMTP_USE_TLS', 'true').lower() in {'1', 'true', 'yes'} and not use_ssl:
                client.starttls(context=ssl.create_default_context())
            username = _setting('SMTP_USERNAME')
            if username:
                client.login(username, _setting('SMTP_PASSWORD'))
            client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise RegistrationSetupError(
            'email_authentication_failed',
            'We could not sign in to the email service. Please choose WhatsApp or contact support.',
        ) from exc
    except Exception as exc:
        raise RegistrationSetupError(
            'email_delivery_failed',
            'We could not send the email code. Check your email address, choose WhatsApp, or contact support.',
        ) from exc


def _phone_to_openwa(phone, country):
    return ContactValidator.to_openwa_chat_id(phone, country)


def _openwa_session_ready(base, session_id, headers):
    """Return whether the configured multi-session OpenWA session can send.

    A disconnected session otherwise produces an HTTP 400 from its send route,
    which is indistinguishable from a malformed recipient unless we check it
    first.  This check intentionally returns only a boolean; it never logs a
    phone number, message body, API key, or verification code.
    """
    request = Request(
        base + '/api/sessions/' + quote(session_id, safe=''), headers=headers,
        method='GET'
    )
    try:
        with urlopen(request, timeout=float(_setting('OPENWA_TIMEOUT', '10'))) as response:
            session_data = json.loads(response.read().decode() or '{}')
        return str(session_data.get('status') or '').strip().lower() == 'ready'
    except (HTTPError, URLError, ValueError, json.JSONDecodeError):
        return False


def _ensure_openwa_session_ready(base, session_id, headers):
    """Ask OpenWA to recover its session, then check it a few times.

    The gateway owns the WhatsApp browser and must perform the actual startup.
    This makes the normal post-restart recovery automatic without allowing the
    registration request to wait indefinitely.  A QR relink remains a manual
    operation when WhatsApp has invalidated the saved browser session.
    """
    if _openwa_session_ready(base, session_id, headers):
        return True

    start_request = Request(
        base + '/api/sessions/' + quote(session_id, safe='') + '/start',
        headers=headers, method='POST'
    )
    try:
        # The gateway may take up to a minute to initialize Chromium.  A short
        # client timeout lets initialization continue without holding a signup
        # request open for the whole duration.
        with urlopen(start_request, timeout=3):
            pass
    except HTTPError as exc:
        # 400 means it is already starting/started; either way polling below is
        # the reliable source of truth.
        if exc.code not in {400}:
            current_app.logger.warning(
                'OpenWA session start request failed status=%s', exc.code
            )
    except (URLError, TimeoutError, OSError):
        # A timed-out start request is expected while OpenWA starts its engine.
        pass

    for _ in range(4):
        time.sleep(1)
        if _openwa_session_ready(base, session_id, headers):
            return True
    return False


def start_configured_openwa_session():
    """Start the configured OpenWA session during Dealuxe application boot.

    This is deliberately callable from a background thread.  OpenWA can take
    time to initialize its browser, and a failed QR authentication must be
    recorded as an operational issue rather than discovered by a player trying
    to register.
    """
    if not current_app.config.get('OPENWA_REGISTRATION_CODES_ENABLED'):
        return
    if _setting('OPENWA_API_MODE', 'multi_session').lower() != 'multi_session':
        print('[OPENWA] Startup session check skipped: this OpenWA mode has no managed session.')
        return
    base = _setting('OPENWA_API_URL').replace('\\:', ':').replace('\\/', '/').rstrip('/\\')
    session_id = _setting('OPENWA_SESSION_ID')
    parsed_base = urlsplit(base)
    if not base or not session_id or parsed_base.scheme not in {'http', 'https'} or not parsed_base.hostname:
        print('[OPENWA] Startup session check failed: OpenWA URL or session ID is not configured.')
        return
    headers = {'Content-Type': 'application/json'}
    api_key = _setting('OPENWA_API_KEY')
    if api_key:
        headers['X-API-Key'] = api_key
    if _ensure_openwa_session_ready(base, session_id, headers):
        print('[OPENWA] Configured WhatsApp session is ready.')
    else:
        print('[OPENWA] Configured WhatsApp session could not start. Open OpenWA, reconnect the session, and scan its QR code if requested.')


def _send_whatsapp(phone, country, code):
    if not current_app.config.get('OPENWA_REGISTRATION_CODES_ENABLED'):
        raise RegistrationSetupError(
            'whatsapp_not_configured',
            'WhatsApp verification is not available right now. Please choose email or contact support.',
        )
    # Tolerate common .env copy/paste escapes while rejecting malformed URLs.
    base = (
        _setting('OPENWA_API_URL')
        .replace('\\:', ':')
        .replace('\\/', '/')
        .rstrip('/\\')
    )
    if not base:
        raise RegistrationSetupError(
            'whatsapp_not_configured',
            'WhatsApp verification is not available right now. Please choose email or contact support.',
        )
    parsed_base = urlsplit(base)
    if parsed_base.scheme not in {'http', 'https'} or not parsed_base.hostname:
        raise RegistrationSetupError(
            'whatsapp_invalid_api_url',
            'The OpenWA address is not valid. Please contact support.',
        )
    mode = _setting('OPENWA_API_MODE', 'multi_session').lower()
    if mode == 'multi_session':
        session_id = _setting('OPENWA_SESSION_ID')
        if not session_id:
            raise RegistrationSetupError(
                'whatsapp_session_not_configured',
                'OpenWA is missing its session ID. Please contact support to finish setup.',
            )
        path = (
            '/api/sessions/' + quote(session_id, safe='')
            + '/messages/send-text'
        )
        body = {
            'chatId': _phone_to_openwa(phone, country),
            'text': f'Your Dealuxe registration code is {code}. It expires in 5 minutes.',
        }
    elif mode == 'v5':
        path = '/api/messages/sendText'
        body = {'to': _phone_to_openwa(phone, country), 'content': f'Your Dealuxe registration code is {code}. It expires in 5 minutes.', 'options': {}}
    elif mode == 'v4':
        path = '/api/sendText'
        body = {'to': _phone_to_openwa(phone, country), 'text': f'Your Dealuxe registration code is {code}. It expires in 5 minutes.'}
    else:
        raise RegistrationSetupError(
            'whatsapp_api_mode_invalid',
            'OpenWA API mode is not configured correctly. Please contact support.',
        )
    headers = {'Content-Type': 'application/json'}
    api_key = _setting('OPENWA_API_KEY')
    if api_key:
        headers['X-API-Key'] = api_key
    if mode == 'multi_session' and not _openwa_session_ready(base, session_id, headers):
        raise RegistrationSetupError(
            'whatsapp_not_ready',
            'WhatsApp verification is temporarily unavailable because the WhatsApp connection is not ready. Please try again shortly or contact support.',
        )
    req = Request(base + path, data=json.dumps(body).encode(), headers=headers, method='POST')
    try:
        with urlopen(req, timeout=float(_setting('OPENWA_TIMEOUT', '10'))) as response:
            payload = json.loads(response.read().decode() or '{}')
            
            if response.status >= 300 or payload.get('success') is False:
                raise ValueError('provider_rejected')
    except HTTPError as exc:
        status = exc.code
        if status in {401, 403}:
            code_name = 'whatsapp_auth_failed'
            message = 'OpenWA rejected its API key. Please contact support to check the WhatsApp connection.'
        elif status == 404:
            if mode == 'multi_session':
                code_name = 'whatsapp_session_or_route_not_found'
                message = 'OpenWA could not find the configured session or message route. Please check the OpenWA setup.'
            else:
                code_name = 'whatsapp_endpoint_not_found'
                message = 'The OpenWA API address or version does not match. Please contact support.'
        elif status == 400:
            code_name = 'whatsapp_request_rejected'
            message = 'OpenWA rejected the phone number or message format. Check the number and try again.'
        elif status == 503:
            code_name = 'whatsapp_not_ready'
            message = 'WhatsApp is still connecting. Please wait a moment and try again.'
        else:
            code_name = 'whatsapp_delivery_failed'
            message = 'OpenWA could not accept the message. Please try again or contact support.'
        raise RegistrationSetupError(
            code_name, message, provider_status=status
        ) from exc
    except URLError as exc:
        raise RegistrationSetupError(
            'whatsapp_unreachable',
            'The app cannot reach OpenWA right now. Please try again or contact support.',
        ) from exc
    except RegistrationSetupError:
        raise
    except Exception as exc:
        raise RegistrationSetupError(
            'whatsapp_delivery_failed',
            'We could not send the WhatsApp code. Check your number, choose email, or contact support.',
        ) from exc


def create_challenge(*, channel, recipient, pending_data, purpose='registration'):
    """Create and deliver a short-lived verification challenge for one purpose."""
    if purpose not in {'registration', 'password_reset'}:
        raise ValueError('Unsupported verification purpose.')
    now = datetime.now()
    code = f'{secrets.randbelow(1_000_000):06d}'
    token = secrets.token_urlsafe(32)
    challenge = RegistrationVerification(
        challenge_token_hash=_digest(token), purpose=purpose,
        channel=channel, recipient=recipient, code_hash=_digest(token + ':' + code),
        pending_data=json.dumps(pending_data), expires_at=now + CODE_LIFETIME,
        resend_after=now + RESEND_DELAY,
    )
    try:
        db.session.add(challenge)
        db.session.flush()
    except Exception as exc:
        db.session.rollback()
        raise RegistrationSetupError(
            'registration_storage_failed',
            'We could not start registration because of a temporary server issue. Please try again later.',
        ) from exc
    try:
        if channel == 'email':
            _send_email(recipient, code)
        elif channel == 'whatsapp':
            _send_whatsapp(pending_data.get('phone'), pending_data.get('country'), code)
        else:
            raise ValueError('Choose email or WhatsApp for your verification code')
    except Exception:
        db.session.rollback()
        raise
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise RegistrationSetupError(
            'registration_storage_failed',
            'We could not finish setting up registration. Please try again later or contact support.',
        ) from exc
    return token, challenge


def find_challenge(token, purpose='registration'):
    if not token:
        return None
    return RegistrationVerification.query.filter_by(
        challenge_token_hash=_digest(token), purpose=purpose, consumed_at=None
    ).first()


def verify_code_for_token(challenge, token, code):
    now = datetime.now()
    if challenge.expires_at <= now:
        return False, 'Verification code expired. Please register again.'
    if challenge.attempts >= MAX_ATTEMPTS:
        return False, 'Too many incorrect codes. Please register again.'
    challenge.attempts += 1
    valid = hmac.compare_digest(challenge.code_hash, _digest(token + ':' + str(code or '').strip()))
    if not valid:
        db.session.commit()
    return (True, None) if valid else (False, 'That verification code is incorrect.')
