"""Request correlation, safe failures, and privacy-minimized JSON audit logs."""

from collections import Counter
from datetime import datetime, timezone
from functools import wraps
import hashlib
import hmac
from html import escape
import inspect
import json
import os
import re
import secrets
from threading import Lock
import time

from flask import Response, current_app, g, has_request_context, jsonify, request, session
from werkzeug.exceptions import HTTPException


_REQUEST_ID_RE = re.compile(r'^req_[a-f0-9]{24}$')
_SAFE_TOKEN_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,120}$')
_SENSITIVE_KEY_RE = re.compile(
    r'(password|passwd|secret|token|cookie|authorization|message|caption|email|'
    r'phone|contact|identity|id_number|document|payload|body|query|address)',
    re.IGNORECASE,
)


def _new_request_id():
    return 'req_' + secrets.token_hex(12)


def current_request_id():
    if not has_request_context():
        return None
    value = getattr(g, 'security_request_id', None)
    return value if value and _REQUEST_ID_RE.match(value) else None


def _safe_text(value, limit=160):
    text = ''.join(
        character if character >= ' ' and character != '\x7f' else ' '
        for character in str(value or '')
    ).strip()
    if not _SAFE_TOKEN_RE.match(text):
        return '[redacted]'
    return text[:limit]


def _safe_details(details):
    safe = {}
    for raw_key, value in (details or {}).items():
        key = _safe_text(raw_key, limit=64)
        if key == '[redacted]' or _SENSITIVE_KEY_RE.search(key):
            continue
        if isinstance(value, (list, tuple)):
            safe[key] = [_safe_text(item) for item in value[:20]]
        elif isinstance(value, bool) or value is None:
            safe[key] = value
        elif isinstance(value, (int, float)):
            safe[key] = value
        else:
            safe[key] = _safe_text(value)
    return safe


class StructuredAuditWriter:
    """Small fail-safe JSON-lines writer with bounded rotation and retention."""

    def __init__(self, path, max_bytes, backup_count, retention_days, clock=None):
        self.path = os.path.abspath(path)
        self.max_bytes = int(max_bytes)
        self.backup_count = int(backup_count)
        self.retention_days = int(retention_days)
        self.clock = clock or time.time
        self._lock = Lock()
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        self._prune_expired()

    def _prune_expired(self):
        cutoff = self.clock() - (self.retention_days * 86400)
        for index in range(1, self.backup_count + 1):
            rotated = f'{self.path}.{index}'
            try:
                if os.path.exists(rotated) and os.path.getmtime(rotated) < cutoff:
                    os.remove(rotated)
            except OSError:
                pass

    def _rotate_if_needed(self, encoded_size):
        current_size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        if current_size + encoded_size <= self.max_bytes:
            return
        oldest = f'{self.path}.{self.backup_count}'
        if os.path.exists(oldest):
            os.remove(oldest)
        for index in range(self.backup_count - 1, 0, -1):
            source = f'{self.path}.{index}'
            if os.path.exists(source):
                os.replace(source, f'{self.path}.{index + 1}')
        if os.path.exists(self.path):
            os.replace(self.path, f'{self.path}.1')

    def write(self, record):
        line = json.dumps(
            record, sort_keys=True, separators=(',', ':'), ensure_ascii=True
        ) + '\n'
        encoded_size = len(line.encode('utf-8'))
        with self._lock:
            self._rotate_if_needed(encoded_size)
            with open(self.path, 'a', encoding='utf-8', newline='\n') as handle:
                handle.write(line)


class SecurityObservability:
    def __init__(self, app, config, extension, writer=None):
        self.app = app
        self.config = config
        self.extension = extension
        self.counters = Counter()
        self._counter_lock = Lock()
        self._digest_key = str(app.config['SECRET_KEY']).encode('utf-8')
        self.writer = writer
        if self.writer is None and config.security_audit_mode != 'off':
            try:
                self.writer = StructuredAuditWriter(
                    config.security_audit_file,
                    config.security_audit_max_bytes,
                    config.security_audit_backup_count,
                    config.security_audit_retention_days,
                )
            except Exception:
                self.writer = None
                self.counters['write_failures'] += 1
        extension['audit_counts'] = self.counters
        extension['observability'] = self

    def _actor_hash(self):
        if not has_request_context():
            return None
        user_id = session.get('user_id')
        source = f'user:{user_id}' if user_id is not None else (
            f'network:{request.remote_addr or "unknown"}'
        )
        return hmac.new(
            self._digest_key,
            source.encode('utf-8', errors='replace'),
            hashlib.sha256,
        ).hexdigest()

    def record(
        self,
        event,
        *,
        channel='http',
        category='application',
        outcome='observed',
        status=None,
        endpoint=None,
        duration_ms=None,
        details=None,
    ):
        if self.config.security_audit_mode == 'off':
            return False
        record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'request_id': current_request_id(),
            'event': _safe_text(event),
            'channel': _safe_text(channel),
            'category': _safe_text(category),
            'outcome': _safe_text(outcome),
            'method': _safe_text(request.method) if has_request_context() else None,
            'endpoint': _safe_text(
                endpoint
                or (request.endpoint if has_request_context() else '<background>')
                or '<unknown>'
            ),
            'status': int(status) if status is not None else None,
            'actor_hash': self._actor_hash(),
        }
        if duration_ms is not None:
            record['duration_ms'] = round(float(duration_ms), 3)
        safe_details = _safe_details(details)
        if safe_details:
            record['details'] = safe_details
        try:
            if self.writer is None:
                raise OSError('security audit writer unavailable')
            self.writer.write(record)
            with self._counter_lock:
                self.counters['written'] += 1
                self.counters[f'event:{record["event"]}'] += 1
            return True
        except Exception:
            with self._counter_lock:
                self.counters['write_failures'] += 1
            return False


def audit_security_event(event, **fields):
    """Write through the active observer, never raising into application work."""
    try:
        observer = current_app.extensions.get('security', {}).get('observability')
        return bool(observer and observer.record(event, **fields))
    except Exception:
        return False


def safe_internal_error(
    message='Request could not be completed', code='request_failed', extra=None
):
    """Return a stable internal-error response without exception or secret text."""
    request_id = current_request_id() or _new_request_id()
    audit_security_event(
        'application_error',
        category='internal_error',
        outcome='failed',
        status=500,
    )
    payload = {}
    for raw_key, value in (extra or {}).items():
        key = _safe_text(raw_key, limit=64)
        if (
            key in {'[redacted]', 'error', 'code', 'request_id'}
            or _SENSITIVE_KEY_RE.search(key)
        ):
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            payload[key] = value
    payload.update({'error': message, 'code': code, 'request_id': request_id})
    if request.path.startswith('/api/') or request.is_json:
        return jsonify(payload), 500
    body = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<title>Request could not be completed</title></head><body>'
        '<main><h1>Request could not be completed</h1>'
        '<p>Please try again. If the problem continues, give support this reference:</p>'
        f'<p><code>{escape(request_id)}</code></p></main></body></html>'
    )
    return Response(body, status=500, content_type='text/html; charset=utf-8')


def install_observability(app, socketio, config, extension, writer=None):
    observer = SecurityObservability(app, config, extension, writer=writer)

    @app.before_request
    def establish_request_context():
        if config.security_audit_mode == 'off':
            return None
        g.security_request_id = _new_request_id()
        g.security_request_started = time.perf_counter()
        return None

    @app.after_request
    def finalize_request(response):
        request_id = current_request_id()
        if request_id:
            response.headers['X-Request-ID'] = request_id
            should_record = (
                config.security_audit_mode == 'enforce'
                or response.status_code >= 400
            )
            if should_record:
                started = getattr(g, 'security_request_started', None)
                duration_ms = (
                    (time.perf_counter() - started) * 1000
                    if started is not None else None
                )
                observer.record(
                    'http_request',
                    category='request',
                    outcome='completed' if response.status_code < 400 else 'failed',
                    status=response.status_code,
                    duration_ms=duration_ms,
                )
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        if isinstance(exc, HTTPException) and (exc.code or 500) < 500:
            return exc
        request_id = current_request_id() or _new_request_id()
        if not current_request_id():
            g.security_request_id = request_id
        app.logger.error(
            'Unhandled application failure request_id=%s exception_type=%s',
            request_id,
            type(exc).__name__,
        )
        observer.record(
            'unhandled_exception',
            category='internal_error',
            outcome='failed',
            status=500,
            details={'exception_type': type(exc).__name__},
        )
        return safe_internal_error()

    if socketio is None or not hasattr(socketio, 'on'):
        return observer

    original_on = socketio.on

    def observed_on(message, namespace=None):
        register = original_on(message, namespace=namespace)

        def decorate(handler):
            @wraps(handler)
            def observed_handler(*args, **kwargs):
                call_args = args
                call_kwargs = kwargs
                if message in {'connect', 'disconnect'} and (args or kwargs):
                    try:
                        inspect.signature(handler).bind(*args, **kwargs)
                    except (TypeError, ValueError):
                        try:
                            inspect.signature(handler).bind()
                        except (TypeError, ValueError):
                            pass
                        else:
                            call_args = ()
                            call_kwargs = {}
                if config.security_audit_mode == 'off':
                    return handler(*call_args, **call_kwargs)
                g.security_request_id = _new_request_id()
                started = time.perf_counter()
                try:
                    result = handler(*call_args, **call_kwargs)
                    if config.security_audit_mode == 'enforce':
                        observer.record(
                            'socket_event',
                            channel='socket',
                            category='socket_event',
                            outcome='completed',
                            endpoint=message,
                            duration_ms=(time.perf_counter() - started) * 1000,
                        )
                    return result
                except Exception as exc:
                    app.logger.error(
                        'Unhandled Socket.IO failure request_id=%s event=%s '
                        'exception_type=%s',
                        current_request_id(),
                        _safe_text(message),
                        type(exc).__name__,
                    )
                    observer.record(
                        'socket_exception',
                        channel='socket',
                        category='internal_error',
                        outcome='failed',
                        endpoint=message,
                        details={'exception_type': type(exc).__name__},
                    )
                    if message == 'connect':
                        return False
                    from flask_socketio import emit
                    emit('security_error', {
                        'error': 'Request could not be completed',
                        'code': 'request_failed',
                        'request_id': current_request_id(),
                    })
                    return None

            return register(observed_handler)

        return decorate

    socketio.on = observed_on
    extension['socketio_observed_on_original'] = original_on
    return observer


def read_security_audit(
    path, *, tail=200, request_id=None, event=None, category=None,
    backup_count=7,
):
    """Read a bounded, already-sanitized administrator view of JSON audit lines."""
    limit = max(1, min(int(tail), 1000))
    paths = []
    for index in range(max(0, int(backup_count)), 0, -1):
        rotated = f'{path}.{index}'
        if os.path.isfile(rotated):
            paths.append(rotated)
    if os.path.isfile(path):
        paths.append(path)
    records = []
    for candidate in paths:
        try:
            with open(candidate, 'r', encoding='utf-8', errors='replace') as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if request_id and record.get('request_id') != request_id:
                        continue
                    if event and record.get('event') != event:
                        continue
                    if category and record.get('category') != category:
                        continue
                    records.append(record)
        except OSError:
            continue
    return records[-limit:]
