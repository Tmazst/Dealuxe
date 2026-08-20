"""
Tests for the strong external payment reference (Transaction.external_ref_id).

Verifies:
  - Tournament entry initiation generates + persists a strong UUID reference
    and sends it to the gateway as `reference` / metadata.external_ref_id
    (never the small internal integer id).
  - The payment callback maps back to the transaction via external_ref_id.
  - Legacy callbacks carrying only the integer transaction_id still resolve.
"""
import os
import unittest
import uuid

os.environ['ENV'] = 'development'

from app import app
from database import (
    db,
    User,
    Player,
    Transaction,
    TX_ENTRY_FEE,
    create_tournament_record,
    add_tournament_participant,
)
from services.payment_service import payment_service
from controllers.tournament_controller import _charge_tournament_entry


class TestPaymentExternalRef(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = False  # boolean False (string 'false' is truthy)
        app.config['MOJAPOS_WEBHOOK_SECRET'] = 'test-secret'
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.user = User(username='payer', email='payer@test.com', phone='+26876000000')
        self.user.set_password('pw')
        db.session.add(self.user)
        db.session.flush()
        db.session.add(Player(user_id=self.user.id, real_balance=100.0))
        db.session.commit()

        self._orig_make_request = payment_service._make_request
        self.client = app.test_client()

    def tearDown(self):
        payment_service._make_request = self._orig_make_request
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _make_tournament(self):
        return create_tournament_record(
            creator_id=self.user.id,
            tournament_type='standard',
            tournament_name='Payment Cup',
            entry_fee=10.0,
            max_players=4,
            is_auto_lock=False,
        )

    # -------------------------
    # Initiation
    # -------------------------

    def test_charge_creates_strong_external_ref_and_sends_it_to_gateway(self):
        captured = {}

        def fake_make_request(endpoint, method='POST', data=None):
            captured['endpoint'] = endpoint
            captured['data'] = data
            return {
                'status': 'success',
                'transaction_id': 'mojapos_txn_123',
                'payment_url': 'https://pay.example/x',
            }

        payment_service._make_request = fake_make_request

        tournament = self._make_tournament()
        paid, charge_result = _charge_tournament_entry(
            self.user.id, tournament.entry_fee, tournament.id, tournament.tournament_code
        )

        self.assertTrue(paid)
        self.assertTrue(charge_result['payment_required'])
        self.assertEqual(charge_result['external_transaction_id'], 'mojapos_txn_123')

        tx = Transaction.query.filter_by(
            tournament_id=tournament.id, transaction_type=TX_ENTRY_FEE
        ).first()
        self.assertIsNotNone(tx)
        self.assertIsNotNone(tx.external_ref_id)
        self.assertGreater(len(tx.external_ref_id), 8)
        # A strong reference must NOT be a guessable short integer.
        self.assertFalse(tx.external_ref_id.isdigit())

        payload = captured['data']
        self.assertEqual(captured['endpoint'], '/payments/initiate')
        self.assertEqual(payload['reference'], tx.external_ref_id)
        self.assertEqual(payload['metadata']['external_ref_id'], tx.external_ref_id)
        self.assertNotIn('transaction_id', payload['metadata'])

        # The gateway's own txn id is stored for idempotency.
        db.session.refresh(tx)
        self.assertEqual(tx.description, 'mojapos_txn_123')

    # -------------------------
    # Callback mapping
    # -------------------------

    def _post_callback(self, payload):
        signature = payment_service._generate_signature(payload)
        return self.client.post(
            '/api/payment/callback',
            json=payload,
            headers={'X-Signature': signature},
        )

    def test_entry_callback_maps_by_external_ref_id(self):
        tournament = self._make_tournament()
        participant = add_tournament_participant(
            tournament.id, self.user.id, payment_status='pending', payment_method='wallet'
        )
        participant.status = 'pending'

        ref = uuid.uuid4().hex[:12]
        tx = Transaction(
            player_id=self.user.player.id,
            transaction_type=TX_ENTRY_FEE,
            amount=10.0,
            balance_type='real',
            balance_before=100.0,
            balance_after=100.0,
            tournament_id=tournament.id,
            external_ref_id=ref,
            description='Tournament entry #1 (pending)',
        )
        db.session.add(tx)
        db.session.commit()

        payload = {
            'transaction_id': 'mojapos_txn_abc',
            'reference': ref,
            'status': 'completed',
            'amount': 10.0,
            'phone_number': '+26876000000',
            'timestamp': '2026-01-01T00:00:00',
            'metadata': {
                'transaction_type': 'tournament_entry',
                'external_ref_id': ref,
                'user_id': str(self.user.id),
                'tournament_code': tournament.tournament_code,
            },
        }
        r = self._post_callback(payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'received')

        db.session.refresh(participant)
        self.assertEqual(participant.status, 'registered')
        self.assertEqual(participant.payment_status, 'completed')
        self.assertEqual(participant.external_payment_id, ref)

        db.session.refresh(tx)
        self.assertEqual(tx.description, 'mojapos_txn_abc')

    def test_entry_callback_legacy_integer_id_fallback(self):
        """Pre-external_ref_id payments carry only the integer id in metadata."""
        tournament = self._make_tournament()
        participant = add_tournament_participant(
            tournament.id, self.user.id, payment_status='pending', payment_method='wallet'
        )
        participant.status = 'pending'

        tx = Transaction(
            player_id=self.user.player.id,
            transaction_type=TX_ENTRY_FEE,
            amount=10.0,
            balance_type='real',
            balance_before=100.0,
            balance_after=100.0,
            tournament_id=tournament.id,
            description='Tournament entry #1 (pending)',
        )
        db.session.add(tx)
        db.session.commit()

        payload = {
            'transaction_id': 'mojapos_txn_legacy',
            'reference': 'entry_legacy',
            'status': 'completed',
            'amount': 10.0,
            'metadata': {
                'transaction_type': 'tournament_entry',
                'transaction_id': str(tx.id),
                'user_id': str(self.user.id),
                'tournament_code': tournament.tournament_code,
            },
        }
        r = self._post_callback(payload)
        self.assertEqual(r.status_code, 200)

        db.session.refresh(participant)
        self.assertEqual(participant.status, 'registered')
        self.assertEqual(participant.payment_status, 'completed')

    def test_callback_rejects_bad_signature(self):
        tournament = self._make_tournament()
        payload = {
            'transaction_id': 'mojapos_txn_x',
            'status': 'completed',
            'amount': 10.0,
            'metadata': {
                'transaction_type': 'tournament_entry',
                'external_ref_id': uuid.uuid4().hex[:12],
                'user_id': str(self.user.id),
                'tournament_code': tournament.tournament_code,
            },
        }
        r = self.client.post(
            '/api/payment/callback',
            json=payload,
            headers={'X-Signature': 'wrong-signature'},
        )
        self.assertEqual(r.status_code, 401)


if __name__ == '__main__':
    unittest.main()

