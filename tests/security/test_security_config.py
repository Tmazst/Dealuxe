import unittest

from config import build_pilot_economy_config, build_runtime_security_config


class RuntimeSecurityConfigTests(unittest.TestCase):
    def test_local_defaults_are_non_wildcard_and_generate_session_secret(self):
        config = build_runtime_security_config({'ENV': 'development'})

        self.assertTrue(config['SESSION_SECRET_GENERATED'])
        self.assertGreaterEqual(len(config['SECRET_KEY']), 32)
        self.assertNotIn('*', config['SOCKETIO_ALLOWED_ORIGINS'])
        self.assertEqual(
            config['SOCKETIO_ALLOWED_ORIGINS'],
            ['http://127.0.0.1:5000', 'http://localhost:5000'],
        )
        self.assertEqual(config['REQUEST_SECURITY_MODE'], 'monitor')
        self.assertTrue(config['REQUEST_SECURITY_CHECK_FETCH_METADATA'])
        self.assertTrue(config['REQUEST_SECURITY_CHECK_ORIGIN'])
        self.assertTrue(config['REQUEST_SECURITY_DETECT_CLI_CLIENTS'])
        self.assertEqual(config['SESSION_COOKIE_SECURITY_MODE'], 'pilot')
        self.assertTrue(config['SESSION_COOKIE_HTTPONLY'])
        self.assertFalse(config['SESSION_COOKIE_SECURE'])
        self.assertEqual(config['SESSION_COOKIE_SAMESITE'], 'Lax')
        self.assertEqual(config['SESSION_ROTATION_MODE'], 'monitor')
        self.assertEqual(config['CSRF_SECURITY_MODE'], 'monitor')

    def test_production_requires_explicit_session_secret(self):
        with self.assertRaisesRegex(RuntimeError, 'FLASK_SECRET_KEY'):
            build_runtime_security_config({'ENV': 'production'})

    def test_wildcard_socket_origin_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Wildcard'):
            build_runtime_security_config({
                'ENV': 'development',
                'SOCKETIO_ALLOWED_ORIGINS': '*',
            })

    def test_production_requires_explicit_redis_url(self):
        with self.assertRaisesRegex(RuntimeError, 'REDIS_URL'):
            build_runtime_security_config({
                'ENV': 'production',
                'FLASK_SECRET_KEY': 's' * 48,
                'SOCKETIO_ALLOWED_ORIGINS': 'https://dealuxe.example',
                'MOJAPOS_MOCK_MODE': 'true',
            })

    def test_live_production_payments_require_verified_webhooks(self):
        base = {
            'ENV': 'production',
            'FLASK_SECRET_KEY': 's' * 48,
            'SOCKETIO_ALLOWED_ORIGINS': 'https://dealuxe.example',
            'REDIS_URL': 'redis://private-redis:6379/0',
            'MOJAPOS_MOCK_MODE': 'false',
        }

        with self.assertRaisesRegex(RuntimeError, 'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE'):
            build_runtime_security_config(base)

        base['MOJAPOS_VERIFY_WEBHOOK_SIGNATURE'] = 'true'
        with self.assertRaisesRegex(RuntimeError, 'MOJAPOS_WEBHOOK_SECRET'):
            build_runtime_security_config(base)

        base['MOJAPOS_WEBHOOK_SECRET'] = 'webhook-secret'
        config = build_runtime_security_config(base)
        self.assertEqual(config['APP_ENV'], 'production')

    def test_origin_list_is_trimmed_and_deduplicated(self):
        config = build_runtime_security_config({
            'ENV': 'test',
            'FLASK_SECRET_KEY': 'test-secret',
            'SOCKETIO_ALLOWED_ORIGINS': (
                'https://one.example/, https://two.example, https://one.example'
            ),
        })

        self.assertEqual(
            config['SOCKETIO_ALLOWED_ORIGINS'],
            ['https://one.example', 'https://two.example'],
        )

    def test_request_security_modes_and_origins_are_configurable(self):
        config = build_runtime_security_config({
            'ENV': 'test',
            'FLASK_SECRET_KEY': 'test-secret',
            'SOCKETIO_ALLOWED_ORIGINS': 'https://socket.example',
            'REQUEST_SECURITY_MODE': 'enforce',
            'REQUEST_SECURITY_TRUSTED_ORIGINS': (
                'https://app.example/, https://app.example'
            ),
            'REQUEST_SECURITY_CHECK_FETCH_METADATA': 'false',
            'REQUEST_SECURITY_CHECK_ORIGIN': 'true',
            'REQUEST_SECURITY_DETECT_CLI_CLIENTS': 'false',
            'REQUEST_SECURITY_ALLOW_SAME_SITE': 'true',
            'REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS': (
                'api.health, api.import'
            ),
        })

        self.assertEqual(config['REQUEST_SECURITY_MODE'], 'enforce')
        self.assertEqual(
            config['REQUEST_SECURITY_TRUSTED_ORIGINS'],
            ['https://app.example'],
        )
        self.assertFalse(config['REQUEST_SECURITY_CHECK_FETCH_METADATA'])
        self.assertTrue(config['REQUEST_SECURITY_CHECK_ORIGIN'])
        self.assertFalse(config['REQUEST_SECURITY_DETECT_CLI_CLIENTS'])
        self.assertTrue(config['REQUEST_SECURITY_ALLOW_SAME_SITE'])
        self.assertEqual(
            config['REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS'],
            ['api.health', 'api.import'],
        )

    def test_invalid_request_security_configuration_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'REQUEST_SECURITY_MODE'):
            build_runtime_security_config({
                'ENV': 'test',
                'REQUEST_SECURITY_MODE': 'sometimes',
            })

        with self.assertRaisesRegex(RuntimeError, 'Wildcard request-security'):
            build_runtime_security_config({
                'ENV': 'test',
                'REQUEST_SECURITY_TRUSTED_ORIGINS': '*',
            })

        with self.assertRaisesRegex(RuntimeError, 'does not allow wildcards'):
            build_runtime_security_config({
                'ENV': 'test',
                'REQUEST_SECURITY_ADDITIONAL_MACHINE_ENDPOINTS': 'api.*',
            })

    def test_cookie_csrf_and_rotation_modes_are_independently_configurable(self):
        config = build_runtime_security_config({
            'ENV': 'test',
            'SESSION_COOKIE_SECURITY_MODE': 'enforce',
            'SESSION_COOKIE_SAMESITE': 'strict',
            'SESSION_ROTATION_MODE': 'off',
            'CSRF_SECURITY_MODE': 'enforce',
            'CSRF_TOKEN_TIME_LIMIT_SECONDS': '900',
            'CSRF_ADDITIONAL_EXEMPT_ENDPOINTS': 'verified.webhook',
        })

        self.assertTrue(config['SESSION_COOKIE_SECURE'])
        self.assertTrue(config['SESSION_COOKIE_HTTPONLY'])
        self.assertEqual(config['SESSION_COOKIE_SAMESITE'], 'Strict')
        self.assertEqual(config['SESSION_ROTATION_MODE'], 'off')
        self.assertEqual(config['CSRF_SECURITY_MODE'], 'enforce')
        self.assertTrue(config['WTF_CSRF_ENABLED'])
        self.assertEqual(config['CSRF_TOKEN_TIME_LIMIT_SECONDS'], 900)
        self.assertEqual(
            config['CSRF_ADDITIONAL_EXEMPT_ENDPOINTS'], ['verified.webhook']
        )

    def test_invalid_cookie_csrf_and_rotation_modes_fail_closed(self):
        cases = (
            ({'SESSION_COOKIE_SECURITY_MODE': 'sometimes'}, 'SESSION_COOKIE_SECURITY_MODE'),
            ({'SESSION_COOKIE_SAMESITE': 'None'}, 'SESSION_COOKIE_SAMESITE'),
            ({'SESSION_ROTATION_MODE': 'sometimes'}, 'SESSION_ROTATION_MODE'),
            ({'CSRF_SECURITY_MODE': 'sometimes'}, 'CSRF_SECURITY_MODE'),
            ({'CSRF_TOKEN_TIME_LIMIT_SECONDS': '0'}, 'CSRF_TOKEN_TIME_LIMIT_SECONDS'),
            ({'CSRF_ADDITIONAL_EXEMPT_ENDPOINTS': 'api.*'}, 'does not allow wildcards'),
        )
        for settings, message in cases:
            with self.subTest(settings=settings):
                with self.assertRaisesRegex(RuntimeError, message):
                    build_runtime_security_config({'ENV': 'test', **settings})


class PilotEconomyConfigTests(unittest.TestCase):
    def test_pilot_defaults_to_credits_without_cash_or_paid_entry(self):
        config = build_pilot_economy_config({'PILOT_MODE': 'true'})

        self.assertTrue(config['PILOT_CREDITS_ENABLED'])
        self.assertFalse(config['PAID_TOURNAMENT_ENTRY_ENABLED'])
        self.assertFalse(config['CASH_PRIZES_ENABLED'])
        self.assertEqual(config['PILOT_TOURNAMENT_ENTRY_COST'], 10.0)

    def test_pilot_rejects_paid_entry_and_cash_prizes(self):
        with self.assertRaisesRegex(RuntimeError, 'Paid tournament entry'):
            build_pilot_economy_config({
                'PILOT_MODE': 'true',
                'PAID_TOURNAMENT_ENTRY_ENABLED': 'true',
            })

        with self.assertRaisesRegex(RuntimeError, 'Cash prizes'):
            build_pilot_economy_config({
                'PILOT_MODE': 'true',
                'CASH_PRIZES_ENABLED': 'true',
            })

    def test_version_three_hard_disables_cup_cash_payouts(self):
        with self.assertRaisesRegex(RuntimeError, 'CUP_CASH_PAYOUTS_ENABLED'):
            build_pilot_economy_config({
                'CUP_CASH_PAYOUTS_ENABLED': 'true',
            })


if __name__ == '__main__':
    unittest.main()
