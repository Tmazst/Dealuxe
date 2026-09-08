"""Configurable browser response headers and privacy-safe CSP reporting."""

from collections import Counter
import json
import re

from flask import Response, jsonify, request

from .csrf import csrf_exempt_endpoint
from .observability import audit_security_event, current_request_id
from .rate_limit import rate_limit_category
from .request_guard import machine_client_endpoint


CSP_REPORT_PATH = '/api/security/csp-report'
_REPORT_TOKEN_RE = re.compile(r'^[a-z0-9_-]{1,80}$', re.IGNORECASE)


def build_csp_policy(config):
    """Build the reviewed MVP policy without accepting raw header text."""
    script_sources = ["'self'", 'https://code.jquery.com']
    if config.csp_allow_inline_scripts:
        script_sources.append("'unsafe-inline'")

    style_sources = [
        "'self'",
        'https://fonts.googleapis.com',
        'https://cdnjs.cloudflare.com',
    ]
    if config.csp_allow_inline_styles:
        style_sources.append("'unsafe-inline'")

    directives = [
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'self'",
        "form-action 'self'",
        'script-src ' + ' '.join(script_sources),
        'style-src ' + ' '.join(style_sources),
        (
            "font-src 'self' data: https://fonts.gstatic.com "
            'https://cdnjs.cloudflare.com'
        ),
        "img-src 'self' data: blob:",
        "connect-src 'self' ws: wss:",
        "media-src 'self'",
        "worker-src 'self' blob:",
        "manifest-src 'self'",
    ]
    if config.csp_reporting_enabled:
        directives.extend([
            f'report-uri {CSP_REPORT_PATH}',
            'report-to csp-endpoint',
        ])
    return '; '.join(directives)


def _report_token(value, fallback='unknown'):
    normalized = str(value or '').strip().lower()
    return normalized if _REPORT_TOKEN_RE.fullmatch(normalized) else fallback


def _blocked_resource_class(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'inline', 'eval'}:
        return normalized
    for scheme in ('data:', 'blob:', 'http:', 'https:', 'ws:', 'wss:'):
        if normalized.startswith(scheme):
            return scheme[:-1]
    return 'other'


def _report_bodies(parsed):
    candidates = parsed if isinstance(parsed, list) else [parsed]
    for candidate in candidates[:20]:
        if not isinstance(candidate, dict):
            continue
        body = candidate.get('csp-report') or candidate.get('body') or candidate
        if isinstance(body, dict):
            yield body


def install_browser_security(app, config, extension):
    """Apply staged browser headers and register the bounded CSP report sink."""
    counters = Counter()
    policy = build_csp_policy(config)
    extension['browser_security_counts'] = counters
    extension['csp_policy'] = policy

    if config.csp_reporting_enabled and config.csp_security_mode != 'off':

        @machine_client_endpoint
        @csrf_exempt_endpoint
        @rate_limit_category('csp_report')
        def security_csp_report():
            declared_size = request.content_length
            if declared_size is not None and declared_size > config.csp_max_report_bytes:
                counters['reports_rejected'] += 1
                audit_security_event(
                    'csp_report_rejected',
                    category='csp',
                    outcome='rejected',
                    status=413,
                    details={'reason': 'too_large'},
                )
                payload = {
                    'error': 'CSP report is too large',
                    'code': 'csp_report_too_large',
                }
                if current_request_id():
                    payload['request_id'] = current_request_id()
                return jsonify(payload), 413

            raw_body = request.stream.read(config.csp_max_report_bytes + 1)
            if len(raw_body) > config.csp_max_report_bytes:
                counters['reports_rejected'] += 1
                return Response(status=413)
            try:
                parsed = json.loads(raw_body.decode('utf-8'))
            except (UnicodeDecodeError, TypeError, ValueError):
                counters['reports_rejected'] += 1
                audit_security_event(
                    'csp_report_rejected',
                    category='csp',
                    outcome='rejected',
                    status=400,
                    details={'reason': 'invalid_json'},
                )
                return Response(status=400)

            accepted = 0
            for body in _report_bodies(parsed):
                directive = _report_token(
                    body.get('effective-directive')
                    or body.get('violated-directive')
                    or body.get('effectiveDirective')
                )
                disposition = _report_token(body.get('disposition'), 'report')
                audit_security_event(
                    'csp_violation',
                    category='csp',
                    outcome='observed',
                    details={
                        'directive': directive,
                        'disposition': disposition,
                        'resource_class': _blocked_resource_class(
                            body.get('blocked-uri') or body.get('blockedURL')
                        ),
                    },
                )
                accepted += 1
            counters['reports_accepted'] += accepted
            return Response(status=204)

        app.add_url_rule(
            CSP_REPORT_PATH,
            endpoint='security_csp_report',
            view_func=security_csp_report,
            methods=['POST'],
        )

    @app.after_request
    def apply_browser_security_headers(response):
        if config.browser_headers_mode != 'off':
            if config.browser_x_content_type_options_enabled:
                response.headers.setdefault('X-Content-Type-Options', 'nosniff')
            if config.browser_x_frame_options_enabled:
                response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
            if config.browser_referrer_policy_enabled:
                response.headers.setdefault(
                    'Referrer-Policy', 'strict-origin-when-cross-origin'
                )
            if config.browser_permissions_policy_enabled:
                response.headers.setdefault(
                    'Permissions-Policy',
                    'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
                )
            response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
            response.headers.setdefault('X-XSS-Protection', '0')
            if (
                config.browser_headers_mode == 'enforce'
                and config.browser_hsts_enabled
                and request.is_secure
            ):
                hsts = f'max-age={config.browser_hsts_max_age_seconds}'
                if config.browser_hsts_include_subdomains:
                    hsts += '; includeSubDomains'
                response.headers.setdefault('Strict-Transport-Security', hsts)

        if config.csp_security_mode != 'off':
            header_name = (
                'Content-Security-Policy'
                if config.csp_security_mode == 'enforce'
                else 'Content-Security-Policy-Report-Only'
            )
            response.headers.setdefault(header_name, policy)
            if config.csp_reporting_enabled:
                response.headers.setdefault(
                    'Reporting-Endpoints',
                    f'csp-endpoint="{CSP_REPORT_PATH}"',
                )

        counters['responses_processed'] += 1
        return response

    return counters
