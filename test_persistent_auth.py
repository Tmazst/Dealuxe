"""Persistent sign-in and account-bound cookie regression checks."""
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from app import app, socketio
from database import db, User, Player
from config import build_runtime_security_config
from flask import Flask, jsonify
from security.session_security import authenticated_session_is_valid


class PersistentAuthTests(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context(); self.ctx.push()
        self.flags = {key:app.config.get(key) for key in (
            'TESTING','WTF_CSRF_ENABLED','PERMANENT_SESSION_LIFETIME','SESSION_COOKIE_SECURE',
            'SESSION_REFRESH_EACH_REQUEST','SESSION_ROTATION_MODE',
        )}
        app.config.update(TESTING=True,WTF_CSRF_ENABLED=False,
                          PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                          SESSION_COOKIE_SECURE=False,SESSION_REFRESH_EACH_REQUEST=True)
        db.drop_all(); db.create_all()
        self.user=User(username='persistent_user',email='persistent@example.test')
        self.user.set_password('ExamplePassword123!')
        db.session.add(self.user); db.session.flush()
        db.session.add(Player(user_id=self.user.id)); db.session.commit()
        self.client=app.test_client()
        self.payload={'username':self.user.username,'password':'ExamplePassword123!'}

    def tearDown(self):
        db.session.remove(); db.drop_all(); app.config.update(self.flags); self.ctx.pop()

    def login(self, client=None):
        response=(client or self.client).post('/api/auth/login',json=self.payload)
        self.assertEqual(response.status_code,200)
        return response

    def test_all_login_entry_points_issue_persistent_cookies(self):
        for endpoint, form in (('/login',True),('/login',False),('/api/auth/login',False)):
            with self.subTest(endpoint=endpoint,form=form):
                client=app.test_client()
                response=client.post(endpoint,**({'data':self.payload} if form else {'json':self.payload}))
                self.assertEqual(response.status_code,302 if form else 200)
                cookie=client.get_cookie(app.config['SESSION_COOKIE_NAME'])
                self.assertIsNotNone(cookie.expires)
                self.assertTrue(cookie.http_only)
                with client.session_transaction() as state:
                    self.assertTrue(state.permanent)
                    self.assertIn('auth_credential_tag',state)
                    self.assertNotEqual(state['auth_credential_tag'],self.user.password_hash)

    def test_reopened_browser_can_use_the_saved_cookie(self):
        self.login()
        cookie=self.client.get_cookie(app.config['SESSION_COOKIE_NAME'])
        reopened=app.test_client()
        reopened.set_cookie(app.config['SESSION_COOKIE_NAME'],cookie.value)
        self.assertEqual(reopened.get('/api/auth/me').status_code,200)
        self.assertEqual(reopened.get('/account').status_code,200)
        # A separate app instance with the same key represents a restarted worker.
        restarted=Flask('restarted-auth-worker')
        restarted.config.update(SECRET_KEY=app.secret_key,PERMANENT_SESSION_LIFETIME=timedelta(days=30))
        @restarted.get('/probe')
        def probe(): return jsonify({'authenticated':authenticated_session_is_valid(self.user)})
        after_restart=restarted.test_client()
        after_restart.set_cookie(app.config['SESSION_COOKIE_NAME'],cookie.value)
        self.assertTrue(after_restart.get('/probe').get_json()['authenticated'])

    def test_activity_renews_sign_in_and_inactivity_expires_it(self):
        now=int(time.time())
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=now): self.login()
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=now+29*86400):
            self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=now+40*86400):
            self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=now+71*86400):
            self.assertEqual(self.client.get('/api/auth/me').status_code,401)

    def test_existing_signed_in_session_is_upgraded_without_reentering_password(self):
        with self.client.session_transaction() as state:
            state['user_id']=self.user.id; state['username']=self.user.username
            state.permanent=False
        self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        self.assertIsNotNone(self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).expires)
        with self.client.session_transaction() as state: self.assertIn('auth_credential_tag',state)

    def test_guest_and_failed_login_are_not_persistently_authenticated(self):
        self.client.get('/api/security/csrf-token')
        cookie=self.client.get_cookie(app.config['SESSION_COOKIE_NAME'])
        self.assertIsNone(cookie.expires)
        response=self.client.post('/api/auth/login',json=dict(self.payload,password='wrong'))
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)

    def test_logout_ends_authentication_for_both_endpoints(self):
        for endpoint in ('/api/auth/logout','/logout'):
            self.login()
            self.client.post(endpoint,json={})
            self.assertEqual(self.client.get('/api/auth/me').status_code,401)
            with self.client.session_transaction() as state: self.assertNotIn('user_id',state)

    def test_disabled_and_deleted_accounts_cannot_restore_persistent_sign_in(self):
        self.login(); self.user.is_active=False; db.session.commit()
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)
        self.user.is_active=True; db.session.commit(); self.login()
        Player.query.filter_by(user_id=self.user.id).delete()
        db.session.delete(self.user); db.session.commit()
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)

    def test_password_change_rejects_an_old_persistent_cookie(self):
        self.login()
        cookie=self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        self.user.set_password('AReplacementPassword123!'); db.session.commit()
        reopened=app.test_client(); reopened.set_cookie(app.config['SESSION_COOKIE_NAME'],cookie)
        self.assertEqual(reopened.get('/api/auth/me').status_code,401)

    def test_reconnected_socket_validates_persistent_credentials(self):
        self.login()
        client=socketio.test_client(app,flask_test_client=self.client)
        connected=[p for p in client.get_received() if p['name']=='connected'][-1]['args'][0]
        self.assertTrue(connected['authenticated']); client.disconnect()
        self.user.set_password('AReplacementPassword123!'); db.session.commit()
        client=socketio.test_client(app,flask_test_client=self.client)
        connected=[p for p in client.get_received() if p['name']=='connected'][-1]['args'][0]
        self.assertFalse(connected['authenticated']); client.disconnect()

    def test_regular_users_do_not_gain_admin_access_when_restored(self):
        self.login()
        cookie=self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        reopened=app.test_client(); reopened.set_cookie(app.config['SESSION_COOKIE_NAME'],cookie)
        self.assertEqual(reopened.get('/api/auth/me').status_code,200)
        self.assertEqual(reopened.get('/api/admin/users').status_code,403)

    def test_secure_cookie_flags_are_preserved(self):
        app.config['SESSION_COOKIE_SECURE']=True
        response=self.login()
        header=response.headers['Set-Cookie']
        self.assertIn('Secure',header); self.assertIn('HttpOnly',header)
        self.assertIn('SameSite=',header); self.assertIn('Expires=',header)


class PersistentAuthConfigTests(unittest.TestCase):
    def test_default_and_configured_lifetimes(self):
        default=build_runtime_security_config({'ENV':'test'})
        self.assertEqual(default['PERMANENT_SESSION_LIFETIME'],timedelta(days=30))
        self.assertTrue(default['SESSION_REFRESH_EACH_REQUEST'])
        configured=build_runtime_security_config({'ENV':'test','AUTH_SESSION_LIFETIME_DAYS':'7'})
        self.assertEqual(configured['PERMANENT_SESSION_LIFETIME'],timedelta(days=7))

    def test_invalid_lifetimes_are_rejected(self):
        for value in ('0','-1','366','never','3.5'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError,'AUTH_SESSION_LIFETIME_DAYS'):
                    build_runtime_security_config({'ENV':'test','AUTH_SESSION_LIFETIME_DAYS':value})
