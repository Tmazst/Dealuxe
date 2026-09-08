"""Mode-aware CSRF tokens for HTML forms and same-origin JSON requests."""

from collections import Counter
from threading import Lock

from flask import jsonify, request
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError

from .observability import audit_security_event, current_request_id


SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def csrf_exempt_endpoint(view):
    """Exclude a reviewed non-browser endpoint from CSRF validation only."""
    view._csrf_security_exempt = True
    return view


def _is_exempt(app, config):
    endpoint = request.endpoint or ''
    view = app.view_functions.get(endpoint)
    if view is not None and getattr(view, '_csrf_security_exempt', False):
        return True
    return endpoint in config.csrf_additional_exempt_endpoints


def _submitted_token():
    return (
        request.form.get('csrf_token')
        or request.headers.get('X-CSRFToken')
        or request.headers.get('X-CSRF-Token')
    )


def install_csrf_guard(app, config, extension):
    """Install token issuance and off/monitor/enforce validation."""
    counters = Counter()
    counter_lock = Lock()
    extension['csrf_counts'] = counters
    app.jinja_env.globals['csrf_token'] = generate_csrf

    def csrf_token_api():
        response = jsonify({'csrf_token': generate_csrf()})
        response.headers['Cache-Control'] = 'no-store'
        return response

    app.add_url_rule(
        '/api/security/csrf-token',
        endpoint='security_csrf_token',
        view_func=csrf_token_api,
        methods=['GET'],
    )

    @app.before_request
    def validate_request_csrf():
        mode = config.csrf_security_mode
        if mode == 'off' or request.method in SAFE_METHODS or _is_exempt(app, config):
            return None

        token = _submitted_token()
        reason = None
        if not token:
            reason = 'missing_token'
        else:
            try:
                validate_csrf(
                    token,
                    time_limit=config.csrf_time_limit_seconds,
                )
            except ValidationError:
                reason = 'invalid_or_expired_token'

        if reason is None:
            with counter_lock:
                counters['accepted'] += 1
            return None

        with counter_lock:
            counters['observed'] += 1
            counters['would_block'] += 1
            counters[f'reason:{reason}'] += 1
        route_rule = request.url_rule.rule if request.url_rule else '<unmatched>'
        app.logger.warning(
            'csrf-security mode=%s method=%s route=%s endpoint=%s reason=%s',
            mode,
            request.method,
            route_rule,
            request.endpoint or '<unknown>',
            reason,
        )
        audit_security_event(
            'csrf_decision',
            category='csrf',
            outcome='blocked' if mode == 'enforce' else 'would_block',
            status=400 if mode == 'enforce' else 200,
            details={'reason': reason},
        )
        if mode != 'enforce':
            return None

        with counter_lock:
            counters['enforced'] += 1
        payload = {
            'error': 'Request rejected because its security token is missing or invalid',
            'code': 'csrf_rejected',
        }
        if current_request_id():
            payload['request_id'] = current_request_id()
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(payload), 400
        return payload['error'], 400
