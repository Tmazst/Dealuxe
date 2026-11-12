"""Authentication-session establishment with configurable rotation."""

import secrets
import time
import hashlib
import hmac

from flask import current_app, session

from .observability import audit_security_event


def _credential_tag(user):
    """Bind persistent sign-in to current credentials without exposing a hash."""
    password_hash = getattr(user, 'password_hash', None)
    if not password_hash:
        return None
    key = current_app.secret_key
    key = key.encode('utf-8') if isinstance(key, str) else key
    message = f'auth-credentials:{user.id}:{password_hash}'.encode('utf-8')
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def authenticated_session_is_valid(user):
    if not user or not user.is_active or user.id != session.get('user_id'):
        return False
    stored_tag = session.get('auth_credential_tag')
    if stored_tag is None:
        return True  # Existing signed sessions are upgraded on their next request.
    expected = _credential_tag(user)
    return bool(expected and isinstance(stored_tag, str) and hmac.compare_digest(stored_tag, expected))


def refresh_authenticated_session(user):
    if not authenticated_session_is_valid(user):
        session.clear()
        return False
    if not session.permanent:
        session.permanent = True
    if 'auth_credential_tag' not in session:
        tag = _credential_tag(user)
        if tag:
            session['auth_credential_tag'] = tag
    return True


def establish_authenticated_session(user):
    """Create the authenticated session according to the configured mode."""
    push_browser = session.get('match_chat_push_browser')
    if push_browser and session.get('user_id') != user.id:
        from hybrid.match_chat_push import revoke_browser_push
        revoke_browser_push()
        push_browser = None
    mode = str(current_app.config.get('SESSION_ROTATION_MODE') or 'monitor').lower()
    audit_outcome = None
    if mode == 'enforce':
        session.clear()
        session['session_nonce'] = secrets.token_urlsafe(24)
        session['session_issued_at'] = int(time.time())
        current_app.logger.info('session-security mode=enforce event=login_rotated')
        audit_outcome = 'rotated'
    elif mode == 'monitor':
        current_app.logger.info('session-security mode=monitor event=login_would_rotate')
        audit_outcome = 'would_rotate'

    session['user_id'] = user.id
    session['username'] = user.username
    if push_browser:
        session['match_chat_push_browser'] = push_browser
    session.permanent = True
    tag = _credential_tag(user)
    if tag:
        session['auth_credential_tag'] = tag
    if audit_outcome:
        audit_security_event(
            'session_rotation',
            category='session',
            outcome=audit_outcome,
        )
