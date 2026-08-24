"""Typed view of the security-sensitive configuration already validated at startup."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SecurityScaffoldConfig:
    environment: str
    local_environment: bool
    socketio_allowed_origins: Tuple[str, ...]
    redis_url_configured: bool
    payment_webhook_verification: bool

    @classmethod
    def from_app(cls, app):
        return cls(
            environment=str(app.config.get('APP_ENV') or 'development'),
            local_environment=bool(app.config.get('IS_LOCAL_ENVIRONMENT')),
            socketio_allowed_origins=tuple(
                app.config.get('SOCKETIO_ALLOWED_ORIGINS') or ()
            ),
            redis_url_configured=bool(app.config.get('REDIS_URL')),
            payment_webhook_verification=bool(
                app.config.get('MOJAPOS_VERIFY_WEBHOOK_SIGNATURE')
            ),
        )
