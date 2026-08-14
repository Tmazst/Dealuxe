import os
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import (
    db,
    User,
    Player,
    Tournament,
    TournamentParticipant,
    TournamentBracket,
    TournamentMatch,
    GameRoom,
    Transaction,
    create_tournament_record,
    add_tournament_participant,
)


class TestLockConsensusAndSchemaAlignment(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = 'true'
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.users = []
        for i in range(1, 5):
            u = User(username=f'player{i}', email=f'player{i}@test.com')
            u.set_password('password123')
            db.session.add(u)
            db.session.flush()
            db.session.add(Player(user_id=u.id, real_balance=100.0))
            self.users.append(u)
        db.session.commit()

        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post('/api/auth/login', json={'username': user.username, 'password': 'password123'})

    def _make_tournament(self, is_auto_lock=False):
        creator = self.users[0]
        t = create_tournament_record(
            creator_id=creator.id,
            tournament_type='standard',
            tournament_name='Consensus Cup',
            entry_fee=10.0,
            max_players=4,
            is_auto_lock=is_auto_lock,
        )
        for u in self.users[:3]:
            add_tournament_participant(t.id, u.id, payment_status='completed', payment_method='wallet')
            tp = TournamentParticipant.query.filter_by(tournament_id=t.id, user_id=u.id).first()
            tp.status = 'registered'
        t.current_player_count = 3
        t.prize_pool_amount = 30.0
        db.session.commit()
        return t

    def test_creator_cannot_vote_and_non_creators_can(self):
        t = self._make_tournament(is_auto_lock=False)

        # Creator voting is rejected (they lock directly)
        self._login(self.users[0])
        r = self.client.post(f'/api/tournaments/{t.id}/vote-lock')
        self.assertEqual(r.status_code, 400)
        self.assertIn('locks directly', r.get_json()['error'])

        # Non-creator votes once
        self._login(self.users[1])
        r = self.client.post(f'/api/tournaments/{t.id}/vote-lock')
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(data['votes_received'], 1)
        self.assertEqual(data['votes_needed'], 2)
        self.assertFalse(data['consensus_reached'])
        self.assertFalse(data['tournament_locked'])

        # Tournament still open
        db.session.refresh(t)
        self.assertEqual(t.status, 'open')

    def test_consensus_locks_tournament(self):
        t = self._make_tournament(is_auto_lock=False)

        self._login(self.users[1])
        r = self.client.post(f'/api/tournaments/{t.id}/vote-lock')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['votes_received'], 1)

        self._login(self.users[2])
        r = self.client.post(f'/api/tournaments/{t.id}/vote-lock')
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(data['consensus_reached'])
        self.assertTrue(data['tournament_locked'])

        # Bracket was built for the current 3 players (with byes)
        db.session.refresh(t)
        self.assertIn(t.status, ('locked', 'in_progress'))
        brackets = TournamentBracket.query.filter_by(tournament_id=t.id).all()
        self.assertGreater(len(brackets), 0)

        # Votes are persisted per participant
        for u in self.users[1:3]:
            tp = TournamentParticipant.query.filter_by(tournament_id=t.id, user_id=u.id).first()
            self.assertTrue(tp.lock_voted)

    def test_auto_lock_tournament_rejects_votes(self):
        t = self._make_tournament(is_auto_lock=True)
        self._login(self.users[1])
        r = self.client.post(f'/api/tournaments/{t.id}/vote-lock')
        self.assertEqual(r.status_code, 400)
        self.assertIn('auto-lock', r.get_json()['error'])

    def test_tournament_serialization_includes_lock_info(self):
        t = self._make_tournament(is_auto_lock=False)
        self._login(self.users[0])
        r = self.client.get('/api/tournaments')
        data = r.get_json()
        arena = next(x for x in data['tournaments'] if x['id'] == t.id)
        self.assertIn('lock', arena)
        self.assertEqual(arena['lock']['mode'], 'manual')
        self.assertEqual(arena['lock']['votes_needed'], 2)
        self.assertEqual(arena['lock']['votes_received'], 0)
        self.assertFalse(arena['is_auto_lock'])

    def test_g1_game_room_marks_tournament_game(self):
        from controllers.tournament_controller import _build_bracket, start_tournament_match_helper

        t = self._make_tournament(is_auto_lock=False)
        _build_bracket(t)
        t.status = 'locked'
        db.session.commit()

        match = TournamentMatch.query.filter_by(tournament_id=t.id).first()
        self.assertIsNotNone(match)

        match, response, code = start_tournament_match_helper(t.id, match.id, user_id=match.player1_id)
        self.assertEqual(code, 200)
        room = GameRoom.query.get(match.game_room_id)
        self.assertIsNotNone(room)
        # G1: tournament rooms are explicitly marked and linked
        self.assertTrue(room.is_tournament_game)
        self.assertEqual(room.tournament_id, t.id)
        self.assertEqual(room.match_id, match.id)

    def test_g2_transaction_types_aligned(self):
        # Mock-mode tournament creation debits the wallet and logs `entry_fee`
        self._login(self.users[0])
        r = self.client.post('/api/tournaments/create', json={
            'tournament_type': 'standard',
            'tournament_name': 'Fee Cup',
            'is_auto_lock': False,
        })
        self.assertEqual(r.status_code, 200)

        from database import get_player_by_user_id
        player = get_player_by_user_id(self.users[0].id)
        txn = Transaction.query.filter_by(player_id=player.id).order_by(Transaction.id.desc()).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.transaction_type, 'entry_fee')


if __name__ == '__main__':
    unittest.main()
