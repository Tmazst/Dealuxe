"""Version 3 security framework scaffold.

Only configuration and extension boundaries live here for now. Enforcement
modules will be introduced incrementally after the pilot economy foundation.
"""

from .config import SecurityScaffoldConfig


def init_security_scaffold(app, socketio=None):
    """Register the lightweight security framework without changing routes."""
    config = SecurityScaffoldConfig.from_app(app)
    app.extensions.setdefault('security', {})
    app.extensions['security'].update({
        'config': config,
        'socketio': socketio,
        'mode': 'scaffold',
    })
    return app.extensions['security']

