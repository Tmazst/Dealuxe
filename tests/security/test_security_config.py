import unittest

from config import build_runtime_security_config


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


if __name__ == '__main__':
    unittest.main()
