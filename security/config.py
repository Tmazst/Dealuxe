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
    request_security_mode: str
    request_security_trusted_origins: Tuple[str, ...]
    request_security_check_fetch_metadata: bool
    request_security_check_origin: bool
    request_security_detect_cli_clients: bool
    request_security_allow_same_site: bool
    request_security_additional_machine_endpoints: Tuple[str, ...]
    cookie_security_mode: str
    csrf_security_mode: str
    csrf_time_limit_seconds: int
    csrf_additional_exempt_endpoints: Tuple[str, ...]
    session_rotation_mode: str

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
            request_security_mode=str(
                app.config.get('REQUEST_SECURITY_MODE') or 'monitor'
            ).lower(),
            request_security_trusted_origins=tuple(
                app.config.get('REQUEST_SECURITY_TRUSTED_ORIGINS') or ()
            ),
            request_security_check_fetch_metadata=bool(
                app.config.get('REQUEST_SECURITY_CHECK_FETCH_METADATA', True)
            ),
            request_security_check_origin=bool(
                app.config.get('REQUEST_SECURITY_CHECK_ORIGIN', True)
            ),
            request_security_detect_cli_clients=bool(
                app.config.get('REQUEST_SECURITY_DETECT_CLI_CLIENTS', True)
            ),
            request_security_allow_same_site=bool(
                app.config.get('REQUEST_SECURITY_ALLOW_SAME_SITE', False)
            ),
            request_security_additional_machine_endpoints=tuple(
                app.config.get('REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS') or ()
            ),
            cookie_security_mode=str(
                app.config.get('SESSION_COOKIE_SECURITY_MODE') or 'pilot'
            ).lower(),
            csrf_security_mode=str(
                app.config.get('CSRF_SECURITY_MODE') or 'monitor'
            ).lower(),
            csrf_time_limit_seconds=int(
                app.config.get('CSRF_TOKEN_TIME_LIMIT_SECONDS') or 3600
            ),
            csrf_additional_exempt_endpoints=tuple(
                app.config.get('CSRF_ADDITIONAL_EXEMPT_ENDPOINTS') or ()
            ),
            session_rotation_mode=str(
                app.config.get('SESSION_ROTATION_MODE') or 'monitor'
            ).lower(),
        )
