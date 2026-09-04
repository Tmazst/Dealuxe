"""Privacy-safe sliding-window limits for sensitive HTTP and Socket.IO traffic."""

from collections import Counter, OrderedDict, deque
from dataclasses import dataclass
from functools import wraps
import hashlib
import hmac
import math
import secrets
from threading import Lock
import time

from flask import current_app, jsonify, request, session


LOGIN_ENDPOINTS = frozenset({
    'auth.login', 'auth.login_api', 'auth.register', 'auth.register_api',
})
PAYMENT_ENDPOINTS = frozenset({
    'payment_callback', 'auth.deposit', 'user.wallet_topup',
    'pricing.purchase_plan_api',
})
UPLOAD_ENDPOINTS = frozenset({
    'user.kyc_upload', 'user.id_photo_upload', 'user.profile_image_upload',
})


@dataclass(frozen=True)
class RateLimitDecision:
    category: str
    allowed: bool
    would_block: bool


class InMemorySlidingWindowStore:
    """Bounded process-local store used for local development and tests."""

    def __init__(self, clock=None, max_keys=10000):
        self.clock = clock or time.time
        self.max_keys = int(max_keys)
        self._windows = OrderedDict()
        self._lock = Lock()

    def consume(self, key, attempts, window_seconds):
        now = float(self.clock())
        cutoff = now - float(window_seconds)
        with self._lock:
            entries = self._windows.pop(key, deque())
            while entries and entries[0] <= cutoff:
                entries.popleft()
            allowed = len(entries) < int(attempts)
            if allowed:
                entries.append(now)
            self._windows[key] = entries
            while len(self._windows) > self.max_keys:
                self._windows.popitem(last=False)
            return allowed


class RedisSlidingWindowStore:
    """Atomic shared sliding-window storage for multi-worker deployments."""

    _CONSUME_SCRIPT = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local member = ARGV[5]
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    redis.call('EXPIRE', key, ttl)
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return 1
"""

    def __init__(self, redis_url):
        import redis

        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self.client.ping()
        self._consume = self.client.register_script(self._CONSUME_SCRIPT)

    def consume(self, key, attempts, window_seconds):
        now_ms = int(time.time() * 1000)
        window_ms = int(window_seconds) * 1000
        result = self._consume(
            keys=[key],
            args=[
                now_ms - window_ms,
                now_ms,
                int(attempts),
                int(math.ceil(window_seconds)) + 1,
                f'{now_ms}:{secrets.token_hex(8)}',
            ],
        )
        return bool(int(result))


def rate_limit_category(category):
    """Assign a reviewed HTTP endpoint to a configured limit category."""
    if category not in {'login', 'payment', 'admin', 'upload'}:
        raise ValueError('Unknown rate-limit category')

    def decorate(view):
        view._rate_limit_category = category
        return view

    return decorate


class ApplicationRateLimiter:
    def __init__(self, app, config, extension, store=None):
        self.app = app
        self.config = config
        self.extension = extension
        self.store = store or self._build_store(app, config)
        self.counters = Counter()
        self._counter_lock = Lock()
        self._digest_key = str(app.config['SECRET_KEY']).encode('utf-8')
        extension['rate_limit_counts'] = self.counters
        extension['rate_limiter'] = self

    @staticmethod
    def _build_store(app, config):
        if config.rate_limit_mode == 'off' or config.rate_limit_storage == 'memory':
            return InMemorySlidingWindowStore()
        try:
            return RedisSlidingWindowStore(app.config['REDIS_URL'])
        except Exception as exc:
            if not config.local_environment and config.rate_limit_mode != 'off':
                raise RuntimeError(
                    'RATE_LIMIT_STORAGE=redis is unavailable; refusing to start '
                    'with rate limiting enabled'
                ) from exc
            app.logger.warning(
                'rate-limit storage=redis unavailable; using bounded local memory'
            )
            return InMemorySlidingWindowStore()

    def _digest(self, scope, identity):
        value = f'{scope}:{identity}'.encode('utf-8', errors='replace')
        return hmac.new(self._digest_key, value, hashlib.sha256).hexdigest()

    def _consume(self, policy_name, scope, identity):
        policy = self.config.rate_limit_policies[policy_name]
        key = 'dealuxe:rate-limit:{0}:{1}'.format(
            policy_name,
            self._digest(scope, identity),
        )
        return self.store.consume(
            key,
            policy['attempts'],
            policy['window_seconds'],
        )

    def _observe(self, category, allowed):
        with self._counter_lock:
            self.counters[f'{category}:observed'] += 1
            if allowed:
                self.counters[f'{category}:accepted'] += 1
            else:
                self.counters['would_block'] += 1
                self.counters[f'{category}:would_block'] += 1

    def _log_limit(self, channel, category, endpoint):
        self.app.logger.warning(
            'rate-limit mode=%s channel=%s category=%s endpoint=%s decision=would_block',
            self.config.rate_limit_mode,
            channel,
            category,
            endpoint,
        )

    def evaluate_http(self, category):
        mode = self.config.rate_limit_mode
        if mode == 'off':
            return RateLimitDecision(category, True, False)

        client_ip = request.remote_addr or 'unknown'
        checks = []
        if category == 'login':
            payload = request.get_json(silent=True) if request.is_json else request.form
            supplied_identity = ''
            if payload:
                supplied_identity = str(
                    payload.get('username') or payload.get('email') or ''
                ).strip().lower()[:254]
            checks = [
                ('login_ip', 'ip', client_ip),
                ('login_account', 'account', supplied_identity or '<missing>'),
            ]
        else:
            identity = session.get('user_id')
            checks = [(category, 'ip', client_ip)]
            if identity is not None:
                checks.append((category, 'user', str(identity)))

        allowed = True
        try:
            for policy_name, scope, identity in checks:
                if not self._consume(policy_name, scope, identity):
                    allowed = False
        except Exception:
            self.app.logger.exception(
                'rate-limit storage failure channel=http category=%s', category
            )
            allowed = False
        self._observe(category, allowed)
        if not allowed:
            self._log_limit('http', category, request.endpoint or '<unknown>')
        would_block = not allowed
        return RateLimitDecision(
            category=category,
            allowed=allowed or mode != 'enforce',
            would_block=would_block,
        )

    def evaluate_socket(self, event_name):
        mode = self.config.rate_limit_mode
        category = 'socket_connect' if event_name == 'connect' else 'socket_event'
        if mode == 'off' or event_name == 'disconnect':
            return RateLimitDecision(category, True, False)

        client_ip = request.remote_addr or 'unknown'
        user_id = session.get('user_id')
        socket_id = getattr(request, 'sid', None)
        allowed = True
        try:
            if category == 'socket_connect':
                allowed = self._consume(category, 'ip', client_ip)
                if user_id is not None:
                    allowed = self._consume(
                        category, 'identity', str(user_id)
                    ) and allowed
            elif user_id is not None:
                # Authenticated gameplay is isolated per account so a venue or
                # mobile carrier NAT cannot make one player's activity consume
                # every other player's event allowance.
                allowed = self._consume(category, 'identity', str(user_id))
            else:
                allowed = self._consume(
                    category, 'identity', str(socket_id or client_ip)
                )
        except Exception:
            self.app.logger.exception(
                'rate-limit storage failure channel=socket category=%s', category
            )
            allowed = False
        self._observe(category, allowed)
        if not allowed:
            self._log_limit('socket', category, event_name)
        return RateLimitDecision(
            category=category,
            allowed=allowed or mode != 'enforce',
            would_block=not allowed,
        )


def _http_category(app):
    endpoint = request.endpoint or ''
    view = app.view_functions.get(endpoint)
    explicit = getattr(view, '_rate_limit_category', None) if view else None
    if explicit:
        return explicit
    if request.method == 'OPTIONS':
        return None
    if endpoint in LOGIN_ENDPOINTS and request.method == 'POST':
        return 'login'
    if endpoint in PAYMENT_ENDPOINTS and request.method not in {'GET', 'HEAD'}:
        return 'payment'
    if endpoint in UPLOAD_ENDPOINTS and request.method not in {'GET', 'HEAD'}:
        return 'upload'
    if endpoint.startswith('admin.') or '.admin_' in endpoint or request.path.startswith('/admin') or request.path.startswith('/api/admin/'):
        return 'admin'
    return None


def install_rate_limits(app, socketio, config, extension, store=None):
    """Install HTTP middleware and wrap subsequently registered socket events."""
    limiter = ApplicationRateLimiter(app, config, extension, store=store)

    @app.before_request
    def enforce_http_rate_limit():
        category = _http_category(app)
        if not category:
            return None
        decision = limiter.evaluate_http(category)
        if decision.allowed:
            return None
        payload = {
            'error': 'Too many requests. Please try again later.',
            'code': 'rate_limited',
        }
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(payload), 429
        return payload['error'], 429

    if socketio is None or not hasattr(socketio, 'on'):
        return limiter

    original_on = socketio.on

    def rate_limited_on(message, namespace=None):
        register = original_on(message, namespace=namespace)

        def decorate(handler):
            @wraps(handler)
            def guarded_handler(*args, **kwargs):
                decision = limiter.evaluate_socket(message)
                if decision.allowed:
                    return handler(*args, **kwargs)
                if message == 'connect':
                    return False
                from flask_socketio import emit
                emit('security_error', {
                    'error': 'Too many requests. Please try again later.',
                    'code': 'rate_limited',
                })
                return None

            return register(guarded_handler)

        return decorate

    socketio.on = rate_limited_on
    extension['socketio_on_original'] = original_on
    return limiter
