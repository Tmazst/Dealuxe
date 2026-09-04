import unittest

from flask import Blueprint, Flask
from flask_socketio import SocketIO, emit

from security import init_security_scaffold, rate_limit_category
from security.rate_limit import InMemorySlidingWindowStore


def _policies(default_attempts=1):
    return {
        name: {'attempts': default_attempts, 'window_seconds': 60}
        for name in (
            'login_ip', 'login_account', 'payment', 'admin', 'upload',
            'socket_connect', 'socket_event',
        )
    }


class RateLimitTests(unittest.TestCase):
    def _app(self, mode='enforce', policies=None, with_socket=False):
        app = Flask(__name__, static_folder=None)
        app.config.update({
            'SECRET_KEY': 'rate-limit-test-secret',
            'APP_ENV': 'test',
            'IS_LOCAL_ENVIRONMENT': True,
            'SOCKETIO_ALLOWED_ORIGINS': ['http://localhost'],
            'REDIS_URL': 'redis://127.0.0.1:6379/0',
            'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE': False,
            'REQUEST_SECURITY_MODE': 'off',
            'REQUEST_SECURITY_TRUSTED_ORIGINS': ['http://localhost'],
            'REQUEST_SECURITY_CHECK_FETCH_METADATA': False,
            'REQUEST_SECURITY_CHECK_ORIGIN': False,
            'REQUEST_SECURITY_DETECT_CLI_CLIENTS': False,
            'REQUEST_SECURITY_ALLOW_SAME_SITE': False,
            'REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS': [],
            'CSRF_SECURITY_MODE': 'off',
            'CSRF_TOKEN_TIME_LIMIT_SECONDS': 3600,
            'CSRF_ADDITIONAL_EXEMPT_ENDPOINTS': [],
            'SESSION_COOKIE_SECURITY_MODE': 'off',
            'SESSION_ROTATION_MODE': 'off',
            'RATE_LIMIT_MODE': mode,
            'RATE_LIMIT_STORAGE': 'memory',
            'RATE_LIMIT_POLICIES': policies or _policies(),
        })
        socketio = SocketIO(app, async_mode='threading') if with_socket else None
        init_security_scaffold(app, socketio=socketio)
        return (app, socketio) if with_socket else app

    def test_sliding_window_reopens_after_expiry(self):
        now = [100.0]
        store = InMemorySlidingWindowStore(clock=lambda: now[0])

        self.assertTrue(store.consume('key', 1, 10))
        self.assertFalse(store.consume('key', 1, 10))
        now[0] = 110.1
        self.assertTrue(store.consume('key', 1, 10))

    def test_login_uses_independent_account_bucket(self):
        policies = _policies(default_attempts=10)
        policies['login_account']['attempts'] = 1
        app = self._app(policies=policies)
        auth = Blueprint('auth', __name__)

        @auth.post('/api/auth/login')
        def login_api():
            return {'attempted': True}

        app.register_blueprint(auth)
        client = app.test_client()
        first = client.post('/api/auth/login', json={'username': 'Target'})
        blocked = client.post('/api/auth/login', json={'username': 'target'})
        other = client.post('/api/auth/login', json={'username': 'other'})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.get_json(), {
            'error': 'Too many requests. Please try again later.',
            'code': 'rate_limited',
        })
        self.assertEqual(other.status_code, 200)

    def test_login_ip_bucket_limits_account_spraying(self):
        policies = _policies(default_attempts=10)
        policies['login_ip']['attempts'] = 2
        app = self._app(policies=policies)
        auth = Blueprint('auth', __name__)

        @auth.post('/login')
        def login():
            return 'attempted'

        app.register_blueprint(auth)
        client = app.test_client()
        self.assertEqual(client.post('/login', data={'username': 'one'}).status_code, 200)
        self.assertEqual(client.post('/login', data={'username': 'two'}).status_code, 200)
        self.assertEqual(client.post('/login', data={'username': 'three'}).status_code, 429)

    def test_monitor_records_but_allows_sensitive_route(self):
        app = self._app(mode='monitor')

        @app.post('/charge')
        @rate_limit_category('payment')
        def charge():
            return {'charged': True}

        client = app.test_client()
        self.assertEqual(client.post('/charge').status_code, 200)
        self.assertEqual(client.post('/charge').status_code, 200)
        self.assertEqual(
            app.extensions['security']['rate_limit_counts']['payment:would_block'],
            1,
        )

    def test_payment_admin_and_upload_categories_enforce(self):
        for category in ('payment', 'admin', 'upload'):
            with self.subTest(category=category):
                app = self._app()

                @app.post('/sensitive')
                @rate_limit_category(category)
                def sensitive():
                    return {'ok': True}

                client = app.test_client()
                self.assertEqual(client.post('/sensitive').status_code, 200)
                self.assertEqual(client.post('/sensitive').status_code, 429)

    def test_known_sensitive_routes_are_classified_without_decorators(self):
        cases = (
            ('payment', '/api/payment/callback', None),
            ('admin', '/api/admin/probe', 'admin'),
            ('upload', '/account/kyc', 'user'),
        )
        for category, path, blueprint_name in cases:
            with self.subTest(category=category):
                app = self._app()
                target = Blueprint(blueprint_name, __name__) if blueprint_name else app

                def endpoint():
                    return {'ok': True}

                endpoint.__name__ = (
                    'payment_callback' if category == 'payment'
                    else 'admin_probe' if category == 'admin'
                    else 'kyc_upload'
                )
                target.add_url_rule(path, view_func=endpoint, methods=['POST'])
                if blueprint_name:
                    app.register_blueprint(target)

                client = app.test_client()
                self.assertEqual(client.post(path).status_code, 200)
                self.assertEqual(client.post(path).status_code, 429)

    def test_off_mode_does_not_count_or_block(self):
        app = self._app(mode='off')

        @app.post('/upload')
        @rate_limit_category('upload')
        def upload():
            return 'ok'

        client = app.test_client()
        self.assertEqual(client.post('/upload').status_code, 200)
        self.assertEqual(client.post('/upload').status_code, 200)
        self.assertEqual(app.extensions['security']['rate_limit_counts'], {})

    def test_socket_events_are_automatically_wrapped(self):
        app, socketio = self._app(with_socket=True)

        @socketio.on('probe')
        def probe(_payload=None):
            emit('probe_result', {'ok': True})

        client = socketio.test_client(app)
        self.assertTrue(client.is_connected())
        client.emit('probe', {})
        first = client.get_received()
        client.emit('probe', {})
        second = client.get_received()

        self.assertTrue(any(item['name'] == 'probe_result' for item in first))
        self.assertTrue(any(
            item['name'] == 'security_error'
            and item['args'][0]['code'] == 'rate_limited'
            for item in second
        ))

    def test_socket_connection_limit_rejects_excess_connection(self):
        policies = _policies(default_attempts=10)
        # Flask-SocketIO's in-process test transport invokes the namespace
        # connect hook twice while establishing one logical test connection.
        policies['socket_connect']['attempts'] = 2
        app, socketio = self._app(policies=policies, with_socket=True)

        @socketio.on('connect')
        def connected():
            return True

        first = socketio.test_client(app)
        second = socketio.test_client(app)

        self.assertTrue(first.is_connected())
        self.assertFalse(second.is_connected())

    def test_socket_monitor_allows_event_after_recording_limit(self):
        app, socketio = self._app(mode='monitor', with_socket=True)
        calls = []

        @socketio.on('probe')
        def probe(_payload=None):
            calls.append(True)

        client = socketio.test_client(app)
        client.emit('probe', {})
        client.emit('probe', {})

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            app.extensions['security']['rate_limit_counts'][
                'socket_event:would_block'
            ],
            1,
        )


if __name__ == '__main__':
    unittest.main()
