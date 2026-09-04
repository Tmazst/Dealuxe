"""Configurable request provenance guard for browser-facing mutations.

This is a defence-in-depth boundary, not proof that a human used a browser.
Raw HTTP clients can forge ordinary headers, so API and webhook routes must
still perform their own authentication, authorization and signature checks.
"""

from collections import Counter
import re
from threading import Lock
from urllib.parse import urlsplit

from flask import jsonify, request


SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
KNOWN_CLI_USER_AGENTS = re.compile(
    r'^(curl/|wget/|python-requests/|python-urllib/|httpie/|postmanruntime/|'
    r'powershell/|libwww-perl/)',
    re.IGNORECASE,
)


def machine_client_endpoint(view):
    """Mark an intentional machine-client route.

    The marker bypasses only this provenance guard. The marked route remains
    responsible for its normal credentials, signature and authorization.
    """
    view._request_security_machine_endpoint = True
    return view


def _normalized_origin(value):
    value = str(value or '').strip().rstrip('/')
    if not value or value == 'null':
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}'


def _referer_origin(value):
    parsed = urlsplit(str(value or '').strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}'


def _is_machine_endpoint(app, config):
    endpoint = request.endpoint or ''
    view = app.view_functions.get(endpoint)
    if view is not None and getattr(
        view, '_request_security_machine_endpoint', False
    ):
        return True
    return endpoint in config.request_security_additional_machine_endpoints


def _violation_reasons(config):
    reasons = []
    user_agent = str(request.headers.get('User-Agent') or '').strip()
    if (
        config.request_security_detect_cli_clients
        and (not user_agent or KNOWN_CLI_USER_AGENTS.search(user_agent))
    ):
        reasons.append('known_or_missing_script_client')

    fetch_site = str(request.headers.get('Sec-Fetch-Site') or '').strip().lower()
    if config.request_security_check_fetch_metadata:
        if fetch_site == 'cross-site':
            reasons.append('cross_site_request')
        elif fetch_site == 'same-site' and not config.request_security_allow_same_site:
            reasons.append('same_site_not_trusted')
        elif fetch_site == 'none':
            reasons.append('non_site_mutation')
        elif fetch_site and fetch_site not in {'same-origin', 'same-site'}:
            reasons.append('invalid_fetch_metadata')

    trusted_origins = {
        origin
        for origin in (
            _normalized_origin(value)
            for value in config.request_security_trusted_origins
        )
        if origin
    }
    origin = _normalized_origin(request.headers.get('Origin'))
    referer = _referer_origin(request.headers.get('Referer'))
    if config.request_security_check_origin:
        if request.headers.get('Origin') and origin not in trusted_origins:
            reasons.append('untrusted_origin')
        elif not origin and request.headers.get('Referer') and referer not in trusted_origins:
            reasons.append('untrusted_referer')
        elif not origin and not referer and not fetch_site:
            reasons.append('missing_browser_provenance')

    return tuple(dict.fromkeys(reasons))


def install_request_guard(app, config, extension):
    """Install the mode-aware Flask request guard and privacy-safe counters."""
    counters = Counter()
    counter_lock = Lock()
    extension['request_guard_counts'] = counters

    @app.before_request
    def enforce_request_provenance():
        mode = config.request_security_mode
        if mode == 'off' or request.method in SAFE_METHODS:
            return None
        if _is_machine_endpoint(app, config):
            with counter_lock:
                counters['machine_endpoint_bypass'] += 1
            return None

        reasons = _violation_reasons(config)
        if not reasons:
            with counter_lock:
                counters['accepted'] += 1
            return None

        with counter_lock:
            counters['observed'] += 1
            counters['would_block'] += 1
            for reason in reasons:
                counters[f'reason:{reason}'] += 1

        route_rule = request.url_rule.rule if request.url_rule else '<unmatched>'
        app.logger.warning(
            'request-security mode=%s method=%s route=%s endpoint=%s reasons=%s',
            mode,
            request.method,
            route_rule,
            request.endpoint or '<unknown>',
            ','.join(reasons),
        )
        if mode != 'enforce':
            return None

        with counter_lock:
            counters['enforced'] += 1
        payload = {
            'error': 'Request rejected by security policy',
            'code': 'request_security_rejected',
        }
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(payload), 403
        return payload['error'], 403

    @app.after_request
    def add_request_guard_vary_header(response):
        if config.request_security_mode != 'off':
            response.vary.add('Origin')
            response.vary.add('Sec-Fetch-Site')
        return response
