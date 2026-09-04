import unittest

from flask import Flask

from security import init_security_scaffold, machine_client_endpoint


class SecurityScaffoldTests(unittest.TestCase):
    def _app(self, mode='monitor', **overrides):
        app = Flask(__name__, static_folder=None)
        app.config.update({
            'APP_ENV': 'development',
            'IS_LOCAL_ENVIRONMENT': True,
            'SOCKETIO_ALLOWED_ORIGINS': ['http://localhost:5000'],
            'REDIS_URL': 'redis://127.0.0.1:6379/0',
            'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE': False,
            'REQUEST_SECURITY_MODE': mode,
            'REQUEST_SECURITY_TRUSTED_ORIGINS': ['http://localhost'],
            'REQUEST_SECURITY_CHECK_FETCH_METADATA': True,
            'REQUEST_SECURITY_CHECK_ORIGIN': True,
            'REQUEST_SECURITY_DETECT_CLI_CLIENTS': True,
            'REQUEST_SECURITY_ALLOW_SAME_SITE': False,
            'REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS': [],
        })
        app.config.update(overrides)
        return app

    def test_monitor_mode_observes_without_blocking(self):
        app = self._app()

        extension = init_security_scaffold(app, socketio='socket-placeholder')

        @app.post('/account/change')
        def change_account():
            return 'changed'

        response = app.test_client().post(
            '/account/change', headers={'User-Agent': 'curl/8.0'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(extension['mode'], 'monitor')
        self.assertEqual(extension['socketio'], 'socket-placeholder')
        self.assertEqual(extension['request_guard_counts']['would_block'], 1)

    def test_enforce_mode_blocks_cli_and_missing_browser_provenance(self):
        app = self._app(mode='enforce')
        extension = init_security_scaffold(app)

        @app.post('/account/change')
        def change_account():
            return 'changed'

        response = app.test_client().post(
            '/account/change', headers={'User-Agent': 'curl/8.0'}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(extension['request_guard_counts']['enforced'], 1)

    def test_enforce_mode_accepts_same_origin_browser_mutation(self):
        app = self._app(mode='enforce')
        init_security_scaffold(app)

        @app.post('/account/change')
        def change_account():
            return 'changed'

        response = app.test_client().post('/account/change', headers={
            'User-Agent': 'Mozilla/5.0',
            'Origin': 'http://localhost',
            'Sec-Fetch-Site': 'same-origin',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('Origin', response.headers.get('Vary', ''))
        self.assertIn('Sec-Fetch-Site', response.headers.get('Vary', ''))

    def test_enforce_mode_rejects_cross_site_mutation(self):
        app = self._app(mode='enforce')
        init_security_scaffold(app)

        @app.post('/api/private-change')
        def private_change():
            return {'ok': True}

        response = app.test_client().post('/api/private-change', headers={
            'User-Agent': 'Mozilla/5.0',
            'Origin': 'https://attacker.example',
            'Sec-Fetch-Site': 'cross-site',
        })

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['code'], 'request_security_rejected')

    def test_invalid_fetch_metadata_cannot_act_as_browser_provenance(self):
        app = self._app(mode='enforce')
        init_security_scaffold(app)

        @app.post('/account/change')
        def change_account():
            return 'changed'

        response = app.test_client().post('/account/change', headers={
            'User-Agent': 'Mozilla/5.0',
            'Sec-Fetch-Site': 'forged-value',
        })

        self.assertEqual(response.status_code, 403)

    def test_machine_client_endpoint_bypasses_only_provenance_guard(self):
        app = self._app(mode='enforce')
        extension = init_security_scaffold(app)

        @app.post('/api/webhook')
        @machine_client_endpoint
        def webhook():
            return {'signature_check': 'still route-owned'}

        response = app.test_client().post(
            '/api/webhook', headers={'User-Agent': 'curl/8.0'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            extension['request_guard_counts']['machine_endpoint_bypass'], 1
        )

    def test_security_can_be_fully_disabled_for_upgrade_testing(self):
        app = self._app(mode='off')
        extension = init_security_scaffold(app)

        @app.post('/account/change')
        def change_account():
            return 'changed'

        response = app.test_client().post('/account/change')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(extension['request_guard_counts']['observed'], 0)


if __name__ == '__main__':
    unittest.main()
