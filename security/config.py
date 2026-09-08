"""Typed view of the security-sensitive configuration already validated at startup."""

from dataclasses import dataclass
from typing import Mapping, Tuple


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
    rate_limit_mode: str
    rate_limit_storage: str
    rate_limit_policies: Mapping[str, Mapping[str, int]]
    security_audit_mode: str
    security_audit_file: str
    security_audit_max_bytes: int
    security_audit_backup_count: int
    security_audit_retention_days: int
    browser_headers_mode: str
    browser_x_frame_options_enabled: bool
    browser_x_content_type_options_enabled: bool
    browser_referrer_policy_enabled: bool
    browser_permissions_policy_enabled: bool
    browser_hsts_enabled: bool
    browser_hsts_max_age_seconds: int
    browser_hsts_include_subdomains: bool
    csp_security_mode: str
    csp_reporting_enabled: bool
    csp_max_report_bytes: int
    csp_allow_inline_scripts: bool
    csp_allow_inline_styles: bool

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
            rate_limit_mode=str(
                app.config.get('RATE_LIMIT_MODE') or 'monitor'
            ).lower(),
            rate_limit_storage=str(
                app.config.get('RATE_LIMIT_STORAGE') or 'memory'
            ).lower(),
            rate_limit_policies=dict(app.config.get('RATE_LIMIT_POLICIES') or {}),
            security_audit_mode=str(
                app.config.get('SECURITY_AUDIT_MODE') or 'monitor'
            ).lower(),
            security_audit_file=str(app.config.get('SECURITY_AUDIT_FILE') or ''),
            security_audit_max_bytes=int(
                app.config.get('SECURITY_AUDIT_MAX_BYTES') or 5 * 1024 * 1024
            ),
            security_audit_backup_count=int(
                app.config.get('SECURITY_AUDIT_BACKUP_COUNT') or 7
            ),
            security_audit_retention_days=int(
                app.config.get('SECURITY_AUDIT_RETENTION_DAYS') or 30
            ),
            browser_headers_mode=str(
                app.config.get('BROWSER_SECURITY_HEADERS_MODE') or 'pilot'
            ).lower(),
            browser_x_frame_options_enabled=bool(
                app.config.get('BROWSER_X_FRAME_OPTIONS_ENABLED', True)
            ),
            browser_x_content_type_options_enabled=bool(
                app.config.get('BROWSER_X_CONTENT_TYPE_OPTIONS_ENABLED', True)
            ),
            browser_referrer_policy_enabled=bool(
                app.config.get('BROWSER_REFERRER_POLICY_ENABLED', True)
            ),
            browser_permissions_policy_enabled=bool(
                app.config.get('BROWSER_PERMISSIONS_POLICY_ENABLED', True)
            ),
            browser_hsts_enabled=bool(
                app.config.get('BROWSER_HSTS_ENABLED', True)
            ),
            browser_hsts_max_age_seconds=int(
                app.config.get('BROWSER_HSTS_MAX_AGE_SECONDS') or 31536000
            ),
            browser_hsts_include_subdomains=bool(
                app.config.get('BROWSER_HSTS_INCLUDE_SUBDOMAINS', False)
            ),
            csp_security_mode=str(
                app.config.get('CSP_SECURITY_MODE') or 'monitor'
            ).lower(),
            csp_reporting_enabled=bool(
                app.config.get('CSP_REPORTING_ENABLED', True)
            ),
            csp_max_report_bytes=int(
                app.config.get('CSP_MAX_REPORT_BYTES') or 16384
            ),
            csp_allow_inline_scripts=bool(
                app.config.get('CSP_ALLOW_INLINE_SCRIPTS', True)
            ),
            csp_allow_inline_styles=bool(
                app.config.get('CSP_ALLOW_INLINE_STYLES', True)
            ),
        )
