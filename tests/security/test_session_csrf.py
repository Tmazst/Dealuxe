import unittest

from flask import Flask, jsonify, session

from security import (
    csrf_exempt_endpoint,
    establish_authenticated_session,
    init_security_scaffold,
)


class _User:
    id = 42
    username = 'session-user'


class SessionAndCsrfSecurityTests(unittest.TestCase):
    def _app(self, csrf_mode='off', rotation_mode='off', cookie_mode='off'):
        app = Flask(__name__, static_folder=None)
        app.config.update({
            'SECRET_KEY': 'test-secret-that-is-long-enough',
            'APP_ENV': 'test',
            'IS_LOCAL_ENVIRONMENT': True,
            'SOCKETIO_ALLOWED_ORIGINS': ['http://localhost'],
            'REDIS_URL': 'redis://127.0.0.1:6379/0',
            'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE': False,
            'REQUEST_SECURITY_MODE': 'off',
            'REQUEST_SECURITY_TRUSTED_ORIGINS': ['http://localhost'],
            'REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS': [],
            'SESSION_COOKIE_SECURITY_MODE': cookie_mode,
            'CSRF_SECURITY_MODE': csrf_mode,
            'CSRF_TOKEN_TIME_LIMIT_SECONDS': 3600,
            'CSRF_ADDITIONAL_EXEMPT_ENDPOINTS': [],
            'SESSION_ROTATION_MODE': rotation_mode,
        })
        init_security_scaffold(app)
        return app

    def test_csrf_monitor_records_missing_token_without_blocking(self):
        app = self._app(csrf_mode='monitor')

        @app.post('/account/change')
        def change():
            return 'changed'

        response = app.test_client().post('/account/change')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            app.extensions['security']['csrf_counts']['would_block'], 1
        )

    def test_csrf_enforce_rejects_missing_token_with_stable_json(self):
        app = self._app(csrf_mode='enforce')

        @app.post('/api/account/change')
        def change():
            return {'changed': True}

        response = app.test_client().post('/api/account/change', json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['code'], 'csrf_rejected')

    def test_csrf_enforce_rejects_malformed_token_with_stable_json(self):
        app = self._app(csrf_mode='enforce')

        @app.post('/api/account/change')
        def change():
            return {'changed': True}

        response = app.test_client().post(
            '/api/account/change',
            json={},
            headers={'X-CSRFToken': 'not-a-valid-token'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['code'], 'csrf_rejected')

    def test_csrf_enforce_accepts_issued_token_for_json_and_form(self):
        app = self._app(csrf_mode='enforce')

        @app.post('/api/account/change')
        def json_change():
            return {'changed': True}

        @app.post('/account/change')
        def form_change():
            return 'changed'

        client = app.test_client()
        token_response = client.get('/api/security/csrf-token')
        token = token_response.get_json()['csrf_token']
        json_response = client.post(
            '/api/account/change', json={}, headers={'X-CSRFToken': token}
        )
        form_response = client.post(
            '/account/change', data={'csrf_token': token}
        )

        self.assertEqual(token_response.headers['Cache-Control'], 'no-store')
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(form_response.status_code, 200)

    def test_only_explicit_csrf_exemption_bypasses_token_check(self):
        app = self._app(csrf_mode='enforce')

        @app.post('/api/webhook')
        @csrf_exempt_endpoint
        def webhook():
            return jsonify({'verified_by_route': True})

        response = app.test_client().post('/api/webhook', json={})

        self.assertEqual(response.status_code, 200)

    def test_enforced_session_rotation_discards_pre_auth_state(self):
        app = self._app(rotation_mode='enforce')

        @app.get('/anonymous')
        def anonymous():
            session['attacker_controlled_marker'] = 'discard-me'
            return 'ready'

        @app.post('/login-test')
        def login_test():
            establish_authenticated_session(_User())
            return jsonify(dict(session))

        client = app.test_client()
        client.get('/anonymous')
        response = client.post('/login-test')
        payload = response.get_json()

        self.assertNotIn('attacker_controlled_marker', payload)
        self.assertEqual(payload['user_id'], 42)
        self.assertEqual(payload['username'], 'session-user')
        self.assertIn('session_nonce', payload)
        self.assertIn('session_issued_at', payload)

    def test_rotation_monitor_preserves_behavior_and_records_intent(self):
        app = self._app(rotation_mode='monitor')

        @app.post('/login-test')
        def login_test():
            session['existing'] = 'kept-during-monitor'
            establish_authenticated_session(_User())
            return jsonify(dict(session))

        payload = app.test_client().post('/login-test').get_json()

        self.assertEqual(payload['existing'], 'kept-during-monitor')
        self.assertNotIn('session_nonce', payload)


if __name__ == '__main__':
    unittest.main()
