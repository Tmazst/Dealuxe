"""Version 3 security framework and request-trust boundary."""

from .config import SecurityScaffoldConfig
from .csrf import csrf_exempt_endpoint, install_csrf_guard
from .request_guard import install_request_guard, machine_client_endpoint
from .rate_limit import install_rate_limits, rate_limit_category
from .observability import (
    audit_security_event,
    current_request_id,
    install_observability,
    safe_internal_error,
)
from .session_security import establish_authenticated_session
from .browser_headers import install_browser_security


def init_security_scaffold(app, socketio=None):
    """Register the configurable request-security framework."""
    config = SecurityScaffoldConfig.from_app(app)
    app.extensions.setdefault('security', {})
    app.extensions['security'].update({
        'config': config,
        'socketio': socketio,
        'mode': config.request_security_mode,
    })
    install_observability(app, socketio, config, app.extensions['security'])
    install_rate_limits(app, socketio, config, app.extensions['security'])
    install_request_guard(app, config, app.extensions['security'])
    install_csrf_guard(app, config, app.extensions['security'])
    install_browser_security(app, config, app.extensions['security'])
    return app.extensions['security']


__all__ = [
    'SecurityScaffoldConfig',
    'init_security_scaffold',
    'machine_client_endpoint',
    'csrf_exempt_endpoint',
    'establish_authenticated_session',
    'rate_limit_category',
    'audit_security_event',
    'current_request_id',
    'safe_internal_error',
]

