"""Version 3 security framework and request-trust boundary."""

from .config import SecurityScaffoldConfig
from .request_guard import install_request_guard, machine_client_endpoint


def init_security_scaffold(app, socketio=None):
    """Register the configurable request-security framework."""
    config = SecurityScaffoldConfig.from_app(app)
    app.extensions.setdefault('security', {})
    app.extensions['security'].update({
        'config': config,
        'socketio': socketio,
        'mode': config.request_security_mode,
    })
    install_request_guard(app, config, app.extensions['security'])
    return app.extensions['security']


__all__ = [
    'SecurityScaffoldConfig',
    'init_security_scaffold',
    'machine_client_endpoint',
]

