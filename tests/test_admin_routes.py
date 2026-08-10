import unittest

from flask import Flask

from admin.routes import admin_bp


class AdminRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(admin_bp)
        self.app.testing = True
        self.client = self.app.test_client()

    def test_dashboard_requires_login(self):
        response = self.client.get('/api/admin/dashboard')
        self.assertEqual(response.status_code, 401)
        self.assertIn('Authentication required', response.get_json()['error'])


if __name__ == '__main__':
    unittest.main()
