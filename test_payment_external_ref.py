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
    get_player_by_user_id,
)
from services.payment_service import payment_service
from controllers.tournament_controller import _charge_tournament_entry
from user.service import initiate_topup


class TestPaymentExternalRef(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = False  # boolean False (string 'false' is truthy)
        app.config['MOJAPOS_WEBHOOK_SECRET'] = 'test-secret'
        app.config['MOJAPOS_VERIFY_WEBHOOK_SIGNATURE'] = True  # exercise the full verification path
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
                'status': 'PENDING',
                'transactionId': '52346890-e826-4093-b371-8503b0b50a19',
                'providerReference': 'b0b88df5-1bdb-40c9-9e9d-89db811ba00a',
            }

        payment_service._make_request = fake_make_request

        # Wallet-FIRST rule: the gateway is only reached when the wallet is short.
        player = get_player_by_user_id(self.user.id)
        player.real_balance = 5.0
        db.session.commit()

        tournament = self._make_tournament()
        paid, charge_result = _charge_tournament_entry(
            self.user.id, tournament.entry_fee, tournament.id, tournament.tournament_code
        )

        self.assertTrue(paid)
        self.assertTrue(charge_result['payment_required'])
        self.assertEqual(charge_result['external_transaction_id'], '52346890-e826-4093-b371-8503b0b50a19')
        self.assertIsNone(charge_result['payment_url'])  # MTN MoMo USSD push - no hosted page

        tx = Transaction.query.filter_by(
            tournament_id=tournament.id, transaction_type=TX_ENTRY_FEE
        ).first()
        self.assertIsNotNone(tx)
        self.assertIsNotNone(tx.external_ref_id)
        self.assertGreater(len(tx.external_ref_id), 8)
        # A strong reference must NOT be a guessable short integer.
        self.assertFalse(tx.external_ref_id.isdigit())

        payload = captured['data']
        self.assertEqual(captured['endpoint'], '/payments/pay')
        self.assertEqual(payload['metadata']['externalId'], tx.external_ref_id)
        self.assertNotIn('reference', payload)
        self.assertNotIn('transaction_id', payload['metadata'])

        # The gateway's own txn id is stored for idempotency.
        db.session.refresh(tx)
        self.assertEqual(tx.description, '52346890-e826-4093-b371-8503b0b50a19')

    def test_charge_wallet_covers_fee_debits_locally_no_gateway(self):
        """Wallet-first: enough balance means local debit, no gateway call."""
        player = get_player_by_user_id(self.user.id)
        player.real_balance = 50.0
        db.session.commit()

        called = []

        def fake_make_request(endpoint, method='POST', data=None):
            called.append(endpoint)
            return {'transactionId': 'x', 'status': 'PENDING'}

        payment_service._make_request = fake_make_request

        tournament = self._make_tournament()
        paid, charge_result = _charge_tournament_entry(
            self.user.id, tournament.entry_fee, tournament.id, tournament.tournament_code
        )

        self.assertTrue(paid)
        self.assertFalse(charge_result['payment_required'])
        self.assertEqual(called, [], "gateway must NOT be called when the wallet covers the fee")

        db.session.refresh(player)
        self.assertEqual(player.real_balance, 40.0)  # E10 debited locally

    def test_charge_insufficient_balance_calls_gateway(self):
        """Wallet-first: short balance -> approach the gateway, hold the fee."""
        player = get_player_by_user_id(self.user.id)
        player.real_balance = 5.0
        db.session.commit()

        called = []

        def fake_make_request(endpoint, method='POST', data=None):
            called.append(endpoint)
            return {
                'status': 'PENDING',
                'transactionId': '52346890-e826-4093-b371-8503b0b50a19',
                'providerReference': 'b0b88df5-1bdb-40c9-9e9d-89db811ba00a',
            }

        payment_service._make_request = fake_make_request

        tournament = self._make_tournament()
        paid, charge_result = _charge_tournament_entry(
            self.user.id, tournament.entry_fee, tournament.id, tournament.tournament_code
        )

        self.assertTrue(paid)
        self.assertTrue(charge_result['payment_required'])
        self.assertEqual(called, ['/payments/pay'], "gateway must be called when the wallet is short")

        # The wallet is NOT debited until the gateway callback confirms.
        db.session.refresh(player)
        self.assertEqual(player.real_balance, 5.0)

        # A pending transaction was recorded with a strong external ref.
        tx = Transaction.query.filter_by(
            tournament_id=tournament.id, transaction_type=TX_ENTRY_FEE
        ).first()
        self.assertIsNotNone(tx)
        self.assertIsNotNone(tx.external_ref_id)
        self.assertEqual(tx.status, 'pending')

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
            'transactionId': 'mojapos_txn_abc',
            'status': 'COMPLETED',
            'amount': 10.0,
            'currency': 'SZL',
            'providerReference': 'b0b88df5-1bdb-40c9-9e9d-89db811ba00a',
            # Real payload only echoes metadata.externalId -- user and tournament
            # must be derived from the transaction row.
            'metadata': {
                'transaction_type': 'tournament_entry',
                'externalId': ref,
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
            'transactionId': 'mojapos_txn_legacy',
            'status': 'COMPLETED',
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
            'transactionId': 'mojapos_txn_x',
            'status': 'COMPLETED',
            'amount': 10.0,
            'metadata': {
                'transaction_type': 'tournament_entry',
                'externalId': uuid.uuid4().hex[:12],
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



    # -------------------------
    # Wallet topup (real gateway path)
    # -------------------------

    def test_wallet_topup_real_mode_creates_pending_txn_and_sends_ref(self):
        captured = {}

        def fake_make_request(endpoint, method='POST', data=None):
            captured['endpoint'] = endpoint
            captured['data'] = data
            return {
                'status': 'PENDING',
                'transactionId': 'mojapos_topup_txn',
                'providerReference': 'b0b88df5-1bdb-40c9-9e9d-89db811ba00a',
            }

        payment_service._make_request = fake_make_request

        result = initiate_topup(self.user, 25.0)

        self.assertTrue(result['success'])
        self.assertEqual(result['external_transaction_id'], 'mojapos_topup_txn')
        self.assertIsNone(result['payment_url'])  # MTN MoMo USSD push - no hosted page
        self.assertIn('external_ref_id', result)

        ref = result['external_ref_id']
        tx = Transaction.query.filter_by(external_ref_id=ref).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.transaction_type, 'wallet_topup')
        self.assertEqual(tx.amount, 25.0)
        self.assertEqual(tx.status, 'pending')

        payload = captured['data']
        self.assertEqual(captured['endpoint'], '/payments/pay')
        self.assertEqual(payload['metadata']['externalId'], ref)
        self.assertNotIn('reference', payload)
        self.assertNotIn('user_id', payload['metadata'])

        db.session.refresh(tx)
        self.assertEqual(tx.description, 'mojapos_topup_txn')

        # The wallet must NOT be credited until the gateway callback confirms.
        player = get_player_by_user_id(self.user.id)
        self.assertEqual(player.real_balance, 100.0)

    def test_wallet_topup_callback_credits_once_and_is_idempotent(self):
        ref = uuid.uuid4().hex[:12]
        tx = Transaction(
            player_id=self.user.player.id,
            transaction_type='wallet_topup',
            amount=25.0,
            balance_type='real',
            balance_before=100.0,
            balance_after=100.0,
            external_ref_id=ref,
            description='Wallet top-up (pending)',
        )
        db.session.add(tx)
        db.session.commit()

        # Real payload only echoes metadata.externalId -- no user_id.
        payload = {
            'transactionId': 'mojapos_topup_abc',
            'status': 'COMPLETED',
            'amount': 25.0,
            'metadata': {
                'transaction_type': 'wallet_topup',
                'externalId': ref,
            },
        }

        # First callback credits the wallet and completes the transaction.
        r1 = self._post_callback(payload)
        self.assertEqual(r1.status_code, 200)
        player = get_player_by_user_id(self.user.id)
        self.assertEqual(player.real_balance, 125.0)
        db.session.refresh(tx)
        self.assertEqual(tx.status, 'completed')

        # Duplicate callback must NOT credit again (top-level idempotency by
        # gateway transaction_id, then per-transaction status guard).
        r2 = self._post_callback(payload)
        self.assertEqual(r2.status_code, 200)
        player2 = get_player_by_user_id(self.user.id)
        self.assertEqual(player2.real_balance, 125.0)

    def test_wallet_topup_callback_unknown_ref_does_not_credit(self):
        payload = {
            'transactionId': 'mojapos_topup_unknown',
            'status': 'COMPLETED',
            'amount': 25.0,
            'metadata': {
                'transaction_type': 'wallet_topup',
                'externalId': uuid.uuid4().hex[:12],
            },
        }
        r = self._post_callback(payload)
        self.assertEqual(r.status_code, 200)
        player = get_player_by_user_id(self.user.id)
        self.assertEqual(player.real_balance, 100.0)


if __name__ == '__main__':
    unittest.main()

