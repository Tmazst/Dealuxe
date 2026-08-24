import unittest

from flask import Flask

from security import init_security_scaffold


class SecurityScaffoldTests(unittest.TestCase):
    def test_scaffold_registers_configuration_without_route_enforcement(self):
        app = Flask(__name__, static_folder=None)
        app.config.update({
            'APP_ENV': 'development',
            'IS_LOCAL_ENVIRONMENT': True,
            'SOCKETIO_ALLOWED_ORIGINS': ['http://localhost:5000'],
            'REDIS_URL': 'redis://127.0.0.1:6379/0',
            'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE': False,
        })

        extension = init_security_scaffold(app, socketio='socket-placeholder')

        self.assertEqual(extension['mode'], 'scaffold')
        self.assertEqual(extension['socketio'], 'socket-placeholder')
        self.assertEqual(
            extension['config'].socketio_allowed_origins,
            ('http://localhost:5000',),
        )
        self.assertEqual(list(app.url_map.iter_rules()), [])


if __name__ == '__main__':
    unittest.main()
