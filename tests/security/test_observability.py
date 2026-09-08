import json
import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from flask_socketio import SocketIO

from config import build_runtime_security_config
from security import audit_security_event, init_security_scaffold, safe_internal_error
from security.config import SecurityScaffoldConfig
from security.observability import (
    StructuredAuditWriter,
    install_observability,
    read_security_audit,
)
from controllers.auth_controller import auth_bp
from controllers.session_controller import session_bp
from admin.routes import admin_bp
from database import User, db


class _BrokenWriter:
    def write(self, _record):
        raise OSError('simulated audit storage outage')


class _Player:
    id = 7
    real_balance = 0
    fake_balance = 100
    fake_balance_expires_at = None

    @staticmethod
    def has_sufficient_balance(_amount, _bet_type):
        return True

    @staticmethod
    def deduct_bet(_amount, _bet_type):
        return None


class SecurityObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix='dealuxe-security-audit-')
        self.audit_path = os.path.join(self.temp_dir.name, 'security.jsonl')
        self.database_apps = []

    def tearDown(self):
        for app in self.database_apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        self.temp_dir.cleanup()

    def _app(self, mode='monitor', with_socket=False):
        app = Flask(__name__, static_folder=None)
        app.config.update(build_runtime_security_config({
            'ENV': 'test',
            'FLASK_SECRET_KEY': 'observability-test-secret',
            'REQUEST_SECURITY_MODE': 'off',
            'CSRF_SECURITY_MODE': 'off',
            'SESSION_ROTATION_MODE': 'off',
            'RATE_LIMIT_MODE': 'off',
            'SECURITY_AUDIT_MODE': mode,
            'SECURITY_AUDIT_FILE': self.audit_path,
            'SECURITY_AUDIT_MAX_BYTES': '65536',
            'SECURITY_AUDIT_BACKUP_COUNT': '2',
            'SECURITY_AUDIT_RETENTION_DAYS': '7',
        }))
        socketio = SocketIO(app, async_mode='threading') if with_socket else None
        init_security_scaffold(app, socketio=socketio)
        return (app, socketio) if with_socket else app

    def _records(self):
        if not os.path.exists(self.audit_path):
            return []
        with open(self.audit_path, 'r', encoding='utf-8') as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_monitor_assigns_request_id_and_records_failed_request(self):
        app = self._app()

        @app.get('/api/problem')
        def problem():
            return {'error': 'controlled'}, 409

        response = app.test_client().get('/api/problem?secret=do-not-log')
        records = self._records()

        self.assertEqual(response.status_code, 409)
        self.assertRegex(response.headers['X-Request-ID'], r'^req_[a-f0-9]{24}$')
        self.assertEqual(records[-1]['request_id'], response.headers['X-Request-ID'])
        rendered = json.dumps(records)
        self.assertNotIn('do-not-log', rendered)
        self.assertNotIn('/api/problem?', rendered)

    def test_enforce_records_successful_request_lifecycle(self):
        app = self._app(mode='enforce')

        @app.get('/health')
        def health():
            return {'ok': True}

        response = app.test_client().get('/health')
        records = self._records()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(
            item['event'] == 'http_request'
            and item['outcome'] == 'completed'
            and item['endpoint'] == 'health'
            for item in records
        ))

    def test_off_mode_adds_no_request_header_or_audit_file(self):
        app = self._app(mode='off')

        @app.get('/controlled')
        def controlled():
            return {'error': 'controlled'}, 400

        response = app.test_client().get('/controlled')

        self.assertEqual(response.status_code, 400)
        self.assertNotIn('X-Request-ID', response.headers)
        self.assertFalse(os.path.exists(self.audit_path))

    def test_unexpected_http_error_is_generic_and_secret_free(self):
        app = self._app()

        @app.post('/api/fail')
        def fail():
            raise RuntimeError('password=private-value user@example.test')

        response = app.test_client().post(
            '/api/fail?token=query-secret',
            json={'password': 'body-secret', 'phone': '26876000000'},
        )
        payload = response.get_json()
        rendered = json.dumps(self._records())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload['code'], 'request_failed')
        self.assertEqual(payload['request_id'], response.headers['X-Request-ID'])
        for secret in (
            'private-value', 'user@example.test', 'query-secret',
            'body-secret', '26876000000',
        ):
            self.assertNotIn(secret, response.get_data(as_text=True))
            self.assertNotIn(secret, rendered)

    def test_sensitive_detail_keys_are_removed(self):
        app = self._app()

        @app.get('/observe')
        def observe():
            audit_security_event(
                'test_decision',
                category='test',
                outcome='observed',
                details={
                    'reason': 'safe_reason',
                    'password': 'private-password',
                    'email': 'private@example.test',
                    'query': 'secret=true',
                },
            )
            return {'ok': True}

        app.test_client().get('/observe')
        record = self._records()[0]

        self.assertEqual(record['details'], {'reason': 'safe_reason'})

    def test_safe_error_extra_cannot_override_or_add_sensitive_text(self):
        app = self._app()

        @app.get('/api/safe-extra')
        def safe_extra():
            return safe_internal_error(extra={
                'success': False,
                'error': 'private override',
                'password': 'private password',
                'detail': 'private detail',
            })

        payload = app.test_client().get('/api/safe-extra').get_json()

        self.assertEqual(payload['error'], 'Request could not be completed')
        self.assertFalse(payload['success'])
        self.assertNotIn('password', payload)
        self.assertNotIn('detail', payload)

    def test_audit_storage_failure_never_changes_response(self):
        app = Flask(__name__, static_folder=None)
        app.config.update(build_runtime_security_config({
            'ENV': 'test',
            'FLASK_SECRET_KEY': 'observability-test-secret',
            'REQUEST_SECURITY_MODE': 'off',
            'CSRF_SECURITY_MODE': 'off',
            'RATE_LIMIT_MODE': 'off',
            'SECURITY_AUDIT_MODE': 'monitor',
            'SECURITY_AUDIT_FILE': self.audit_path,
        }))
        extension = {}
        install_observability(
            app,
            None,
            SecurityScaffoldConfig.from_app(app),
            extension,
            writer=_BrokenWriter(),
        )

        @app.get('/available')
        def available():
            return {'available': True}, 503

        response = app.test_client().get('/available')

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()['available'])
        self.assertEqual(extension['audit_counts']['write_failures'], 1)

    def test_audit_writer_rotates_with_a_bounded_backup_count(self):
        writer = StructuredAuditWriter(
            self.audit_path,
            max_bytes=220,
            backup_count=2,
            retention_days=7,
        )
        for index in range(12):
            writer.write({'event': 'rotation_probe', 'sequence': index})

        self.assertTrue(os.path.isfile(self.audit_path))
        self.assertTrue(os.path.isfile(f'{self.audit_path}.1'))
        self.assertTrue(os.path.isfile(f'{self.audit_path}.2'))
        self.assertFalse(os.path.exists(f'{self.audit_path}.3'))
        for candidate in (
            self.audit_path,
            f'{self.audit_path}.1',
            f'{self.audit_path}.2',
        ):
            with open(candidate, 'r', encoding='utf-8') as handle:
                for line in handle:
                    self.assertEqual(json.loads(line)['event'], 'rotation_probe')

    def test_socket_exception_is_generic_and_keeps_client_connected(self):
        app, socketio = self._app(with_socket=True)

        @socketio.on('explode')
        def explode(_payload=None):
            raise RuntimeError('private socket message')

        client = socketio.test_client(app)
        client.emit('explode', {'message': 'also private'})
        received = client.get_received()
        error = next(item for item in received if item['name'] == 'security_error')
        payload = error['args'][0]

        self.assertTrue(client.is_connected())
        self.assertEqual(payload['code'], 'request_failed')
        self.assertRegex(payload['request_id'], r'^req_[a-f0-9]{24}$')
        self.assertNotIn('private socket message', json.dumps(self._records()))
        self.assertNotIn('also private', json.dumps(self._records()))

    def test_zero_argument_socket_lifecycle_handlers_remain_compatible(self):
        for mode in ('off', 'monitor'):
            with self.subTest(mode=mode):
                app, socketio = self._app(mode=mode, with_socket=True)
                lifecycle = []

                @socketio.on('connect')
                def connect():
                    lifecycle.append('connected')

                @socketio.on('disconnect')
                def disconnect():
                    lifecycle.append('disconnected')

                client = socketio.test_client(app)
                self.assertTrue(client.is_connected())
                client.disconnect()
                self.assertEqual(lifecycle, ['connected', 'disconnected'])

    def test_admin_reader_filters_by_request_id_and_category(self):
        app = self._app(mode='enforce')

        @app.get('/one')
        def one():
            return {'one': True}

        @app.get('/two')
        def two():
            audit_security_event(
                'special_event', category='special', outcome='observed'
            )
            return {'two': True}

        first = app.test_client().get('/one')
        second = app.test_client().get('/two')
        records = read_security_audit(
            self.audit_path,
            tail=100,
            request_id=second.headers['X-Request-ID'],
            category='special',
        )

        self.assertNotEqual(
            first.headers['X-Request-ID'], second.headers['X-Request-ID']
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['event'], 'special_event')

    def test_admin_can_search_security_events_without_exposing_file_path(self):
        app = self._app(mode='enforce')
        database_path = os.path.join(self.temp_dir.name, 'admin.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            f"sqlite:///{database_path.replace(os.sep, '/')}"
        )
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)
        self.database_apps.append(app)
        app.register_blueprint(admin_bp)

        with app.app_context():
            db.create_all()
            admin = User(
                username='security-admin',
                email='security-admin@example.test',
                is_admin=True,
            )
            admin.set_password('not-returned')
            db.session.add(admin)
            db.session.commit()
            admin_id = admin.id

        client = app.test_client()
        with client.session_transaction() as browser_session:
            browser_session['user_id'] = admin_id

        probe = client.get('/missing-security-probe')
        response = client.get(
            '/api/admin/security-events',
            query_string={'request_id': probe.headers['X-Request-ID']},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['mode'], 'enforce')
        self.assertGreaterEqual(payload['total'], 1)
        self.assertTrue(all(
            event['request_id'] == probe.headers['X-Request-ID']
            for event in payload['events']
        ))
        self.assertNotIn('file', payload)

    def test_registration_caught_exception_does_not_leak(self):
        app = self._app()
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)
        app.register_blueprint(auth_bp)
        with patch(
            'controllers.auth_controller.get_user_by_username', return_value=None
        ), patch(
            'controllers.auth_controller.get_user_by_email', return_value=None
        ), patch(
            'controllers.auth_controller._complete_registration',
            side_effect=RuntimeError('database-password-private'),
        ):
            response = app.test_client().post('/api/auth/register', json={
                'username': 'new-user',
                'email': 'new@example.test',
                'password': 'private-password',
            })

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()['code'], 'registration_failed')
        self.assertNotIn('database-password-private', response.get_data(as_text=True))
        self.assertNotIn('private-password', json.dumps(self._records()))

    def test_game_session_caught_exception_does_not_leak(self):
        app = self._app()
        app.register_blueprint(session_bp)
        with patch(
            'controllers.session_controller.get_or_create_demo_player',
            return_value=_Player(),
        ), patch(
            'controllers.session_controller.create_session',
            side_effect=RuntimeError('database-uri-private'),
        ):
            response = app.test_client().post('/api/session/create', json={
                'opponent_type': 'ai',
                'card_count': 6,
                'bet_type': 'fake',
                'bet_amount': 10,
            })

        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()['success'])
        self.assertEqual(response.get_json()['code'], 'game_session_failed')
        self.assertNotIn('database-uri-private', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
