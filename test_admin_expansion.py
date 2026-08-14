import os
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import (
    db,
    User,
    Player,
    Tournament,
    AdminAuditLog,
    Dispute,
    WalletAdjustment,
    create_tournament_record,
    add_tournament_participant,
    get_player_by_user_id,
)


class TestAdminExpansion(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = 'true'
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.admin = User(username='boss', email='boss@test.com', is_admin=True)
        self.admin.set_password('pw')
        db.session.add(self.admin)
        db.session.flush()
        db.session.add(Player(user_id=self.admin.id, real_balance=100.0))

        self.regular = User(username='player1', email='p1@test.com')
        self.regular.set_password('pw')
        db.session.add(self.regular)
        db.session.flush()
        db.session.add(Player(user_id=self.regular.id, real_balance=50.0, fake_balance=10.0))
        db.session.commit()

        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post('/api/auth/login', json={'username': user.username, 'password': 'pw'})

    def test_admin_endpoints_require_admin(self):
        self._login(self.regular)
        r = self.client.get('/api/admin/users')
        self.assertEqual(r.status_code, 403)
        r = self.client.get('/api/admin/audit-logs')
        self.assertEqual(r.status_code, 403)

    def test_wallet_adjust_credits_and_audits(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': 25.0,
            'reason': 'Tournament refund adjustment',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['wallet']['new_balance'], 75.0)

        # Balance persisted
        player = get_player_by_user_id(self.regular.id)
        self.assertEqual(player.real_balance, 75.0)

        # Wallet adjustment row logged
        adj = WalletAdjustment.query.filter_by(user_id=self.regular.id).first()
        self.assertIsNotNone(adj)
        self.assertEqual(adj.delta, 25.0)
        self.assertEqual(adj.reason, 'Tournament refund adjustment')

        # Audit log entry recorded
        log = AdminAuditLog.query.filter_by(action='wallet.adjust').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.admin_user_id, self.admin.id)
        self.assertEqual(log.entity_id, self.regular.id)

    def test_wallet_adjust_rejects_negative_balance(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': -500.0,
            'reason': 'Clawback',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('negative', r.get_json()['error'])

    def test_wallet_adjust_requires_reason(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'fake',
            'delta': 10.0,
        })
        self.assertEqual(r.status_code, 400)

    def test_award_credits(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/users/{self.regular.id}/credits', json={
            'amount': 500,
            'balance_type': 'fake',
            'reason': 'Promotional pack',
        })
        self.assertEqual(r.status_code, 200)
        player = get_player_by_user_id(self.regular.id)
        self.assertEqual(player.fake_balance, 510.0)

    def test_dispute_workflow(self):
        # Player files a dispute (login required, not admin-only)
        self._login(self.regular)
        r = self.client.post('/api/admin/disputes', json={
            'category': 'payment',
            'description': 'Entry fee charged twice',
        })
        self.assertEqual(r.status_code, 201)
        dispute = r.get_json()['dispute']
        self.assertEqual(dispute['status'], 'pending')

        # Admin lists disputes
        self._login(self.admin)
        r = self.client.get('/api/admin/disputes')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()['disputes']), 1)

        # Admin resolves
        r = self.client.post(f"/api/admin/disputes/{dispute['id']}/resolve", json={
            'status': 'resolved',
            'resolution': 'Refunded second charge',
        })
        self.assertEqual(r.status_code, 200)
        resolved = r.get_json()['dispute']
        self.assertEqual(resolved['status'], 'resolved')
        self.assertEqual(resolved['resolved_by'], self.admin.id)

        # Audit logged
        log = AdminAuditLog.query.filter_by(action='dispute.resolved').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.entity_id, dispute['id'])

    def test_audit_logs_endpoint(self):
        self._login(self.admin)
        self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': 5.0,
            'reason': 'Goodwill credit',
        })
        r = self.client.get('/api/admin/audit-logs')
        self.assertEqual(r.status_code, 200)
        logs = r.get_json()['logs']
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]['action'], 'wallet.adjust')
        self.assertEqual(logs[0]['admin_username'], 'boss')

    def test_tournament_force_start_and_complete(self):
        self._login(self.admin)
        with app.app_context():
            t = create_tournament_record(
                creator_id=self.regular.id, tournament_type='standard',
                tournament_name='Admin Cup', entry_fee=10.0, max_players=4,
            )
            for u in (self.admin, self.regular):
                add_tournament_participant(t.id, u.id, payment_status='completed', payment_method='wallet')
            db.session.commit()
            tid = t.id

        # Force-start builds the bracket and moves to in_progress
        r = self.client.post(f'/api/admin/tournaments/{tid}/force-start')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'in_progress')

        # Detail endpoint returns fixtures
        r = self.client.get(f'/api/admin/tournaments/{tid}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('fixtures', r.get_json())
        self.assertIn('participants', r.get_json())

        # Force-complete
        r = self.client.post(f'/api/admin/tournaments/{tid}/complete')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
