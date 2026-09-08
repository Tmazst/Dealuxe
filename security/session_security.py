"""Authentication-session establishment with configurable rotation."""

import secrets
import time

from flask import current_app, session

from .observability import audit_security_event


def establish_authenticated_session(user):
    """Create the authenticated session according to the configured mode."""
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
    if audit_outcome:
        audit_security_event(
            'session_rotation',
            category='session',
            outcome=audit_outcome,
        )
