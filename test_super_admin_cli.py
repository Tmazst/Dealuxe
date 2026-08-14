import unittest

from flask import Flask

from database import (
    User,
    db,
    create_user,
    get_user_by_username,
)
from super_admin_cli import (
    SuperAdminError,
    assign_admin,
    create_super_admin,
    list_users,
    reset_password,
    revoke_admin,
)


def _make_test_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


class TestSuperAdminCLI(unittest.TestCase):
    def setUp(self):
        self.app = _make_test_app()
        with self.app.app_context():
            create_user(username='player1', email='p1@test.com', password='password123')

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_bootstrap_creates_super_admin(self):
        user = create_super_admin(self.app, 'root', 'root@test.com', 'secret99')
        self.assertTrue(user['is_super_admin'])
        self.assertFalse(user['is_admin'])
        with self.app.app_context():
            db_user = get_user_by_username('root')
            self.assertTrue(db_user.is_super_admin)

        # Can only be bootstrapped once
        with self.assertRaises(SuperAdminError):
            create_super_admin(self.app, 'root2', 'root2@test.com', 'secret99')

    def test_bootstrap_rejects_existing_username(self):
        with self.assertRaises(SuperAdminError):
            create_super_admin(self.app, 'player1', 'x@test.com', 'secret99')

    def test_assign_admin_requires_super_admin_password(self):
        create_super_admin(self.app, 'root', 'root@test.com', 'secret99')

        # Wrong password is rejected
        with self.assertRaises(SuperAdminError):
            assign_admin(self.app, 'root', 'wrong-password', 'player1')

        # Correct password promotes the target
        user = assign_admin(self.app, 'root', 'secret99', 'player1')
        self.assertTrue(user['is_admin'])
        with self.app.app_context():
            db_user = get_user_by_username('player1')
            self.assertTrue(db_user.is_admin)

    def test_assign_admin_rejects_non_super(self):
        create_super_admin(self.app, 'root', 'root@test.com', 'secret99')
        # A regular (non-super, non-admin) account cannot assign
        with self.assertRaises(SuperAdminError):
            assign_admin(self.app, 'player1', 'password123', 'root')

    def test_revoke_admin(self):
        create_super_admin(self.app, 'root', 'root@test.com', 'secret99')
        assign_admin(self.app, 'root', 'secret99', 'player1')

        user = revoke_admin(self.app, 'root', 'secret99', 'player1')
        self.assertFalse(user['is_admin'])

        # Revoking a non-admin is rejected
        with self.assertRaises(SuperAdminError):
            revoke_admin(self.app, 'root', 'secret99', 'player1')

    def test_super_admin_cannot_revoke_itself(self):
        create_super_admin(self.app, 'root', 'root@test.com', 'secret99')
        with self.app.app_context():
            root = get_user_by_username('root')
            root.is_admin = True  # super admins are also treated as admins
            db.session.commit()
        with self.assertRaises(SuperAdminError) as ctx:
            revoke_admin(self.app, 'root', 'secret99', 'root')
        self.assertIn('Super admin privileges', str(ctx.exception))

    def test_reset_password(self):
        create_super_admin(self.app, 'root', 'root@test.com', 'secret99')
        reset_password(self.app, 'root', 'secret99', 'player1', 'newpass123')

        with self.app.app_context():
            user = get_user_by_username('player1')
            self.assertFalse(user.check_password('password123'))
            self.assertTrue(user.check_password('newpass123'))

    def test_list_users_includes_roles(self):
        create_super_admin(self.app, 'root', 'root@test.com', 'secret99')
        assign_admin(self.app, 'root', 'secret99', 'player1')

        users = {u['username']: u for u in list_users(self.app)}
        self.assertTrue(users['root']['is_super_admin'])
        self.assertTrue(users['player1']['is_admin'])
        self.assertFalse(users['player1']['is_super_admin'])


if __name__ == '__main__':
    unittest.main()
