import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['ENV'] = 'development'

from app import app
from controllers.tournament_controller import _finalize_tournament, _withdraw_participant
from database import (
    Player,
    Tournament,
    TournamentParticipant,
    TournamentPrizePool,
    Transaction,
    TX_PROMOTIONAL_ENTRY,
    TX_PROMOTIONAL_ENTRY_REVERSAL,
    User,
    db,
)
from services.payment_service import payment_service


class TestPilotTournamentEconomy(unittest.TestCase):
    def setUp(self):
        self.original_flags = {
            key: app.config.get(key)
            for key in (
                'PILOT_MODE',
                'PILOT_CREDITS_ENABLED',
                'PAID_TOURNAMENT_ENTRY_ENABLED',
                'CASH_PRIZES_ENABLED',
                'PILOT_TOURNAMENT_ENTRY_COST',
            )
        }
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            PILOT_MODE=True,
            PILOT_CREDITS_ENABLED=True,
            PAID_TOURNAMENT_ENTRY_ENABLED=False,
            CASH_PRIZES_ENABLED=False,
            PILOT_TOURNAMENT_ENTRY_COST=10.0,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.users = []
        for index in range(2):
            user = User(username=f'pilot{index}', email=f'pilot{index}@test.com')
            user.set_password('password123')
            db.session.add(user)
            db.session.flush()
            db.session.add(Player(
                user_id=user.id,
                real_balance=50.0,
                promotional_credit_balance=10.0,
                promotional_credit_expires_at=datetime.utcnow() + timedelta(days=30),
            ))
            self.users.append(user)
        db.session.commit()
        self.client = app.test_client()
        self.original_request = payment_service._make_request

    def tearDown(self):
        payment_service._make_request = self.original_request
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original_flags)

    def _login(self, user):
        self.client.post('/api/auth/logout')
        response = self.client.post('/api/auth/login', json={
            'username': user.username,
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 200)

    def _create(self):
        self._login(self.users[0])
        return self.client.post('/api/tournaments/create', json={
            'tournament_type': 'standard',
            'tournament_name': 'Pilot Cup Qualifier',
            'start_option': 'seats_filled',
        })

    def test_creation_uses_promotional_credit_and_never_calls_payment_gateway(self):
        payment_service._make_request = lambda *args, **kwargs: self.fail('MojaPOS was called')

        response = self._create()

        self.assertEqual(response.status_code, 200, response.get_json())
        tournament = Tournament.query.one()
        player = Player.query.filter_by(user_id=self.users[0].id).one()
        participant = TournamentParticipant.query.one()
        transaction = Transaction.query.filter_by(transaction_type=TX_PROMOTIONAL_ENTRY).one()
        self.assertEqual(player.real_balance, 50.0)
        self.assertEqual(player.promotional_credit_balance, 0.0)
        self.assertEqual(tournament.prize_pool_amount, 0.0)
        self.assertEqual(participant.payment_method, 'promotional_credit')
        self.assertEqual(transaction.balance_type, 'promotional')
        self.assertFalse(response.get_json()['tournament']['cash_prizes_enabled'])

    def test_public_pilot_pages_use_credit_and_qualification_messaging(self):
        tournament_id = self._create().get_json()['tournament']['id']

        arena = self.client.get('/tournaments').get_data(as_text=True)
        waiting_room = self.client.get(f'/tournaments/{tournament_id}').get_data(as_text=True)
        bracket = self.client.get(f'/tournaments/{tournament_id}/bracket').get_data(as_text=True)
        spectator = self.client.get(
            f'/spectators/tournaments/{tournament_id}'
        ).get_data(as_text=True)

        self.assertIn('Practice. Learn.', arena)
        self.assertIn('E10 promotional credit', arena)
        self.assertIn('Create with E10 credit', arena)
        self.assertNotIn('Prize pool breakdown', arena)
        self.assertNotIn('Create &amp; pay E10.00', arena)
        self.assertIn('Cup qualifier', waiting_room)
        self.assertNotIn('Total Prize Pool', waiting_room)
        self.assertIn('Cup qualifier', bracket)
        self.assertIn('Pilot reward', spectator)

    def test_tournament_detail_api_exposes_pilot_presentation_contract(self):
        tournament_id = self._create().get_json()['tournament']['id']

        response = self.client.get(f'/api/tournaments/{tournament_id}/overview')
        tournament = response.get_json()['tournament']

        self.assertEqual(tournament['entry_balance_type'], 'promotional')
        self.assertFalse(tournament['cash_prizes_enabled'])
        self.assertEqual(tournament['prize_pool_amount'], 0.0)

    def test_duplicate_join_does_not_charge_twice(self):
        response = self._create()
        tournament_id = response.get_json()['tournament']['id']

        response = self.client.post(f'/api/tournaments/{tournament_id}/join')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transaction.query.filter_by(transaction_type=TX_PROMOTIONAL_ENTRY).count(), 1)

    def test_creation_failure_rolls_back_the_credit_debit(self):
        self._login(self.users[0])
        with patch(
            'controllers.tournament_controller._ensure_prize_pool',
            side_effect=RuntimeError('forced failure'),
        ):
            response = self.client.post('/api/tournaments/create', json={
                'tournament_type': 'standard',
                'start_option': 'seats_filled',
            })

        player = Player.query.filter_by(user_id=self.users[0].id).one()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(player.promotional_credit_balance, 10.0)
        self.assertEqual(Tournament.query.count(), 0)
        self.assertEqual(Transaction.query.filter_by(transaction_type=TX_PROMOTIONAL_ENTRY).count(), 0)

    def test_join_requires_active_promotional_credit(self):
        tournament_id = self._create().get_json()['tournament']['id']
        joining_player = Player.query.filter_by(user_id=self.users[1].id).one()
        joining_player.promotional_credit_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        self._login(self.users[1])

        response = self.client.post(f'/api/tournaments/{tournament_id}/join')

        self.assertEqual(response.status_code, 402)
        self.assertEqual(joining_player.real_balance, 50.0)
        self.assertEqual(Transaction.query.filter_by(transaction_type=TX_PROMOTIONAL_ENTRY).count(), 1)
        self.assertIsNone(TournamentParticipant.query.filter_by(
            tournament_id=tournament_id, user_id=self.users[1].id
        ).first())

    def test_withdrawal_reverses_promotional_entry_once(self):
        tournament_id = self._create().get_json()['tournament']['id']
        tournament = Tournament.query.get(tournament_id)
        participant = TournamentParticipant.query.one()
        player = Player.query.filter_by(user_id=self.users[0].id).one()

        ok, error = _withdraw_participant(tournament, participant)
        db.session.commit()

        self.assertTrue(ok, error)
        self.assertEqual(player.promotional_credit_balance, 10.0)
        self.assertEqual(Transaction.query.filter_by(
            transaction_type=TX_PROMOTIONAL_ENTRY_REVERSAL
        ).count(), 1)
        self.assertEqual(tournament.prize_pool_amount, 0.0)

    def test_promotional_tournament_never_awards_real_cash(self):
        tournament_id = self._create().get_json()['tournament']['id']
        tournament = Tournament.query.get(tournament_id)
        tournament.winner_id = self.users[0].id
        prize = TournamentPrizePool.query.filter_by(
            tournament_id=tournament.id, placement=1
        ).one()
        prize.prize_percentage = 100.0
        prize.prize_amount = 100.0
        db.session.commit()

        _finalize_tournament(tournament)
        db.session.commit()

        player = Player.query.filter_by(user_id=self.users[0].id).one()
        participant = TournamentParticipant.query.one()
        self.assertEqual(player.real_balance, 50.0)
        self.assertEqual(participant.prize_awarded, 0.0)


if __name__ == '__main__':
    unittest.main()
