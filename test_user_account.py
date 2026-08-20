"""
Tests for the user account area: dedicated account page, profile editing,
KYC / ID photo uploads, protected file serving, and mock-mode wallet topup.
"""
import io
import os
import shutil
import tempfile
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import db, User, Player, get_player_by_user_id


class TestUserAccount(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = 'true'
        app.config['WTF_CSRF_ENABLED'] = False  # form POST tests don't carry CSRF tokens
        self._tmp_uploads = tempfile.mkdtemp()
        app.config['UPLOAD_FOLDER'] = self._tmp_uploads
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.user = User(username='alice', email='alice@test.com', phone='+26876000000')
        self.user.set_password('pw')
        db.session.add(self.user)
        db.session.flush()
        db.session.add(Player(user_id=self.user.id, real_balance=50.0, fake_balance=10.0))

        self.other = User(username='bob', email='bob@test.com', phone='+26877000000')
        self.other.set_password('pw')
        db.session.add(self.other)
        db.session.flush()
        db.session.add(Player(user_id=self.other.id, real_balance=0.0))
        db.session.commit()

        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        shutil.rmtree(self._tmp_uploads, ignore_errors=True)

    def _login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post('/api/auth/login', json={'username': user.username, 'password': 'pw'})

    @staticmethod
    def _png_file(name='id.png'):
        return (io.BytesIO(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00'
            b'\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        ), name)

    # -------------------------
    # Account page
    # -------------------------

    def test_account_page_requires_login(self):
        r = self.client.get('/account')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers.get('Location', ''))

    def test_account_page_renders_for_logged_in_user(self):
        self._login(self.user)
        r = self.client.get('/account')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'My Account', r.data)
        self.assertIn(b'+26876000000', r.data)

    def test_account_api_returns_profile_and_kyc(self):
        self._login(self.user)
        r = self.client.get('/account/api')
        self.assertEqual(r.status_code, 200)
        account = r.get_json()['account']
        self.assertEqual(account['username'], 'alice')
        self.assertEqual(account['kyc_status'], 'not_submitted')
        self.assertEqual(account['player']['real_balance'], 50.0)

    # -------------------------
    # Profile editing
    # -------------------------

    def test_profile_update(self):
        self._login(self.user)
        r = self.client.post('/account/profile', data={
            'full_name': 'Alice Mamba',
            'phone': '+26876123456',
            'country': 'Eswatini',
            'address': 'Mbabane, Eswatini',
            'date_of_birth': '1990-01-01',
            'id_number': 'ESW123456',
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(self.user)
        self.assertEqual(self.user.full_name, 'Alice Mamba')
        self.assertEqual(self.user.phone, '+26876123456')
        self.assertEqual(self.user.country, 'Eswatini')
        self.assertEqual(self.user.address, 'Mbabane, Eswatini')
        self.assertEqual(self.user.id_number, 'ESW123456')
        self.assertIsNotNone(self.user.date_of_birth)

    def test_profile_update_rejects_phone_already_in_use(self):
        self._login(self.user)
        r = self.client.post('/account/profile', data={
            'full_name': 'Alice',
            'phone': '+26877000000',  # belongs to bob
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(self.user)
        self.assertEqual(self.user.phone, '+26876000000')  # unchanged

    # -------------------------
    # KYC / ID uploads
    # -------------------------

    def test_kyc_and_id_upload_sets_pending_review(self):
        self._login(self.user)
        r = self.client.post('/account/kyc', data={
            'kyc_document': self._png_file('bill.png'),
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(self.user)
        self.assertIsNotNone(self.user.kyc_document_path)

        r = self.client.post('/account/id-photo', data={
            'id_photo': self._png_file('front.png'),
            'id_photo_back': self._png_file('back.png'),
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(self.user)
        self.assertIsNotNone(self.user.id_photo_path)
        self.assertIsNotNone(self.user.id_photo_back_path)
        self.assertEqual(self.user.kyc_status, 'pending_review')

    def test_upload_rejects_disallowed_extension(self):
        self._login(self.user)
        r = self.client.post('/account/id-photo', data={
            'id_photo': (io.BytesIO(b'not an image'), 'evil.txt'),
            'id_photo_back': self._png_file('back.png'),
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        db.session.refresh(self.user)
        self.assertIsNone(self.user.id_photo_path)
        self.assertIsNone(self.user.id_photo_back_path)

    def test_uploads_route_is_owner_only(self):
        self._login(self.user)
        self.client.post('/account/kyc', data={
            'kyc_document': self._png_file('bill.png'),
        }, content_type='multipart/form-data')
        db.session.refresh(self.user)
        path = self.user.kyc_document_path
        self.assertIsNotNone(path)

        # owner can fetch the file
        r = self.client.get('/account/uploads/' + path)
        self.assertEqual(r.status_code, 200)

        # another logged-in user is forbidden
        self._login(self.other)
        r = self.client.get('/account/uploads/' + path)
        self.assertEqual(r.status_code, 403)

        # anonymous is redirected to login
        self.client.post('/api/auth/logout')
        r = self.client.get('/account/uploads/' + path)
        self.assertEqual(r.status_code, 302)

    # -------------------------
    # Wallet topup (mock mode)
    # -------------------------

    def test_wallet_topup_mock_credits_balance(self):
        self._login(self.user)
        before = get_player_by_user_id(self.user.id).real_balance
        r = self.client.post('/account/topup', json={'amount': 25})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get('mock'))
        self.assertEqual(data['new_balance'], before + 25)

    def test_wallet_topup_rejects_invalid_amount(self):
        self._login(self.user)
        r = self.client.post('/account/topup', json={'amount': -5})
        self.assertEqual(r.status_code, 400)

    def test_me_endpoint_exposes_new_fields(self):
        self._login(self.user)
        r = self.client.get('/api/auth/me')
        self.assertEqual(r.status_code, 200)
        user = r.get_json()['user']
        self.assertEqual(user['kyc_status'], 'not_submitted')
        self.assertIn('country', user)
        self.assertIn('id_number', user)


if __name__ == '__main__':
    unittest.main()

