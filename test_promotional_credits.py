import os
import unittest
from datetime import datetime, timedelta

os.environ['ENV'] = 'development'

from app import app
from config import GameConfig
from database import (
    TX_PROMOTIONAL_CREDIT,
    Player,
    Transaction,
    User,
    db,
)


class PromotionalCreditWalletTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_existing_fake_columns_have_promotional_credit_aliases(self):
        user = User(username='legacy', email='legacy@test.com')
        user.set_password('password')
        db.session.add(user)
        db.session.flush()
        player = Player(user_id=user.id, fake_balance=7.5)
        db.session.add(player)
        db.session.commit()

        self.assertEqual(player.promotional_credit_balance, 7.5)
        player.promotional_credit_balance = 9.0
        self.assertEqual(player.fake_balance, 9.0)

    def test_registration_grants_e10_for_30_days_and_audits_it(self):
        response = self.client.post('/api/auth/register', json={
            'username': 'new-player',
            'email': 'new-player@test.com',
            'password': 'password123',
        })

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()['player']
        self.assertEqual(
            payload['promotional_credit_balance'],
            GameConfig.PROMOTIONAL_CREDIT_REGISTRATION_AMOUNT,
        )
        self.assertEqual(payload['fake_balance'], payload['promotional_credit_balance'])
        self.assertTrue(payload['has_active_promotional_credits'])

        expires_at = datetime.fromisoformat(payload['promotional_credit_expires_at'])
        remaining = expires_at - datetime.utcnow()
        self.assertGreater(remaining, timedelta(days=29))
        self.assertLessEqual(remaining, timedelta(days=30))

        transaction = Transaction.query.filter_by(
            transaction_type=TX_PROMOTIONAL_CREDIT
        ).one()
        self.assertEqual(transaction.amount, 10.0)
        self.assertEqual(transaction.balance_type, 'promotional')
        self.assertEqual(transaction.balance_before, 0.0)
        self.assertEqual(transaction.balance_after, 10.0)

    def test_expired_credit_is_replaced_not_accumulated_on_new_grant(self):
        user = User(username='expired', email='expired@test.com')
        user.set_password('password')
        db.session.add(user)
        db.session.flush()
        player = Player(
            user_id=user.id,
            promotional_credit_balance=99.0,
            promotional_credit_expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(player)
        db.session.commit()

        player.grant_promotional_credits(10.0)
        self.assertEqual(player.promotional_credit_balance, 10.0)
        self.assertTrue(player.has_active_promotional_credits())


if __name__ == '__main__':
    unittest.main()
