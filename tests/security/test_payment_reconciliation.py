"""V3-0119 payment callback reconciliation security regressions."""

from concurrent.futures import ThreadPoolExecutor
import copy
import os
import threading
import uuid

os.environ['ENV'] = 'test'

from app import app
from database import (
    Player,
    Tournament,
    TournamentParticipant,
    Transaction,
    TX_ENTRY_FEE,
    TX_PRIZE_AWARD,
    TX_WALLET_TOPUP,
    User,
    db,
)
from services.payment_service import payment_service


def _payload(ref, gateway, amount='25.00', *, event='payment.success',
             environment='LIVE', currency='SZL'):
    success = event == 'payment.success'
    return {
        'id': uuid.uuid4().hex,
        'event': event,
        'environment': environment,
        'data': {
            'transactionId': gateway,
            'status': 'COMPLETED' if success else 'FAILED',
            'amount': amount,
            'currency': currency,
            'providerResponse': {
                'externalId': ref,
                'amount': amount,
                'currency': currency,
                'status': 'SUCCESSFUL' if success else 'FAILED',
            },
        },
    }


def _post(payload):
    with app.app_context():
        signature = payment_service._generate_signature(payload)
    with app.test_client() as client:
        return client.post(
            '/api/payment/callback',
            json=payload,
            headers={'X-Signature': signature},
        )


class TestAtomicPaymentReconciliation:
    def setup_method(self):
        self.original_config = {
            key: app.config.get(key)
            for key in (
                'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE', 'MOJAPOS_WEBHOOK_SECRET',
                'MOJAPOS_EXPECTED_ENVIRONMENT', 'MOJAPOS_EXPECTED_CURRENCY',
                'MOJAPOS_WEBHOOK_RECONCILIATION_MODE',
                'MOJAPOS_WEBHOOK_MAX_BYTES',
            )
        }
        app.config.update(
            TESTING=True,
            MOJAPOS_VERIFY_WEBHOOK_SIGNATURE=True,
            MOJAPOS_WEBHOOK_SECRET='v3-0119-test-secret',
            MOJAPOS_EXPECTED_ENVIRONMENT='LIVE',
            MOJAPOS_EXPECTED_CURRENCY='SZL',
            MOJAPOS_WEBHOOK_RECONCILIATION_MODE='monitor',
            MOJAPOS_WEBHOOK_MAX_BYTES=32768,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        user = User(
            username='atomicpayer', email='atomicpayer@example.test',
            phone='+26876000001',
        )
        user.set_password('test-password')
        db.session.add(user)
        db.session.flush()
        player = Player(user_id=user.id, real_balance=100.0)
        db.session.add(player)
        db.session.commit()
        self.user_id = user.id
        self.player_id = player.id

    def teardown_method(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original_config)

    def _transaction(self, *, amount=25.0, gateway=None,
                     transaction_type=TX_WALLET_TOPUP, tournament_id=None):
        ref = uuid.uuid4().hex
        gateway = gateway or f'gateway-{uuid.uuid4().hex}'
        transaction = Transaction(
            player_id=self.player_id,
            transaction_type=transaction_type,
            amount=amount,
            balance_type='real',
            balance_before=100.0,
            balance_after=100.0,
            external_ref_id=ref,
            gateway_transaction_id=gateway,
            currency='SZL',
            payment_environment='LIVE',
            status='pending',
            tournament_id=tournament_id,
            description='pending external payment',
        )
        db.session.add(transaction)
        db.session.commit()
        return transaction

    def test_simultaneous_replays_credit_wallet_exactly_once(self):
        transaction = self._transaction()
        payload = _payload(
            transaction.external_ref_id,
            transaction.gateway_transaction_id,
        )
        barrier = threading.Barrier(4)

        def send_replay():
            barrier.wait(timeout=5)
            return _post(payload).status_code

        db.session.remove()
        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses = list(executor.map(lambda _index: send_replay(), range(4)))

        assert statuses == [200, 200, 200, 200]
        player = db.session.get(Player, self.player_id)
        transaction = db.session.get(Transaction, transaction.id)
        assert player.real_balance == 125.0
        assert transaction.status == 'completed'
        assert transaction.reconciliation_code == 'settled'
        assert transaction.reconciled_at is not None

    def test_contract_mismatches_do_not_poison_pending_payment(self):
        mutations = (
            lambda body: body['data'].update(amount='24.00'),
            lambda body: (
                body['data'].update(currency='USD'),
                body['data']['providerResponse'].update(currency='USD'),
            ),
            lambda body: body.update(environment='SANDBOX'),
            lambda body: body['data'].update(transactionId='gateway-wrong'),
        )
        for mutate in mutations:
            transaction = self._transaction()
            body = _payload(
                transaction.external_ref_id,
                transaction.gateway_transaction_id,
            )
            mutate(body)
            if body['data']['amount'] != body['data']['providerResponse']['amount']:
                body['data']['providerResponse']['amount'] = body['data']['amount']
            response = _post(body)
            assert response.status_code == 200
            db.session.refresh(transaction)
            assert transaction.status == 'pending'
        assert db.session.get(Player, self.player_id).real_balance == 100.0

    def test_failed_payment_is_terminal_and_never_creates_wallet_value(self):
        transaction = self._transaction()
        failed = _payload(
            transaction.external_ref_id,
            transaction.gateway_transaction_id,
            event='payment.failed',
        )
        assert _post(failed).status_code == 200
        db.session.refresh(transaction)
        assert transaction.status == 'failed'
        assert transaction.reconciliation_code == 'gateway_failed'
        assert db.session.get(Player, self.player_id).real_balance == 100.0

        success = _payload(
            transaction.external_ref_id,
            transaction.gateway_transaction_id,
        )
        assert _post(success).status_code == 200
        assert db.session.get(Player, self.player_id).real_balance == 100.0

    def test_entry_success_and_replay_add_exactly_one_seat_and_fee(self):
        tournament = Tournament(
            tournament_code='ATOMIC-ENTRY',
            tournament_name='Atomic Entry',
            tournament_type='standard',
            creator_id=self.user_id,
            entry_fee=10.0,
            prize_pool_amount=0.0,
            max_players=4,
            current_player_count=0,
            status='open',
            is_auto_lock=False,
        )
        db.session.add(tournament)
        db.session.flush()
        participant = TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.user_id,
            status='pending',
            payment_status='pending',
        )
        db.session.add(participant)
        db.session.commit()
        transaction = self._transaction(
            amount=10.0,
            transaction_type=TX_ENTRY_FEE,
            tournament_id=tournament.id,
        )
        body = _payload(
            transaction.external_ref_id,
            transaction.gateway_transaction_id,
            amount='10.00',
        )

        assert _post(body).status_code == 200
        assert _post(body).status_code == 200
        db.session.refresh(tournament)
        db.session.refresh(participant)
        assert tournament.current_player_count == 1
        assert tournament.prize_pool_amount == 10.0
        assert participant.status == 'registered'
        assert participant.payment_status == 'completed'
        assert transaction.status == 'completed'

    def test_failed_entry_does_not_refund_money_that_was_never_debited(self):
        tournament = Tournament(
            tournament_code='FAILED-ENTRY',
            tournament_name='Failed Entry',
            tournament_type='standard',
            creator_id=self.user_id,
            entry_fee=10.0,
            prize_pool_amount=0.0,
            max_players=4,
            current_player_count=0,
            status='open',
        )
        db.session.add(tournament)
        db.session.flush()
        participant = TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.user_id,
            status='pending',
            payment_status='pending',
        )
        db.session.add(participant)
        db.session.commit()
        transaction = self._transaction(
            amount=10.0,
            transaction_type=TX_ENTRY_FEE,
            tournament_id=tournament.id,
        )
        body = _payload(
            transaction.external_ref_id,
            transaction.gateway_transaction_id,
            amount='10.00',
            event='payment.failed',
        )

        assert _post(body).status_code == 200
        db.session.refresh(participant)
        assert participant.payment_status == 'failed'
        assert db.session.get(Player, self.player_id).real_balance == 100.0
        assert transaction.status == 'failed'

    def test_unknown_unsupported_and_legacy_callbacks_cannot_mutate_state(self):
        unknown = _payload(uuid.uuid4().hex, f'gateway-{uuid.uuid4().hex}')
        assert _post(unknown).status_code == 200

        unsupported = self._transaction(transaction_type=TX_PRIZE_AWARD)
        body = _payload(
            unsupported.external_ref_id,
            unsupported.gateway_transaction_id,
        )
        assert _post(body).status_code == 200
        db.session.refresh(unsupported)
        assert unsupported.status == 'pending'

        legacy = {
            'transactionId': unsupported.gateway_transaction_id,
            'status': 'COMPLETED',
            'amount': 25,
            'metadata': {'transaction_id': unsupported.id},
        }
        assert _post(legacy).status_code == 400
        assert db.session.get(Player, self.player_id).real_balance == 100.0

    def test_provider_disagreement_and_oversized_body_are_rejected(self):
        transaction = self._transaction()
        body = _payload(
            transaction.external_ref_id,
            transaction.gateway_transaction_id,
        )
        body['data']['providerResponse']['amount'] = '26.00'
        assert _post(body).status_code == 400
        db.session.refresh(transaction)
        assert transaction.status == 'pending'

        app.config['MOJAPOS_WEBHOOK_MAX_BYTES'] = 128
        oversized = copy.deepcopy(body)
        oversized['padding'] = 'x' * 256
        assert _post(oversized).status_code == 413
