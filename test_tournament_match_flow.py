import os
import unittest
from datetime import datetime

from app import app
from database import (
    db,
    User,
    Player,
    Tournament,
    TournamentParticipant,
    TournamentBracket,
    TournamentMatch,
    TournamentPrizePool,
    GameRoom,
    create_tournament_record,
    add_tournament_participant,
)
from controllers.tournament_controller import (
    _build_bracket,
    start_tournament_match_helper,
    record_tournament_match_result,
)
from controllers.multiplayer_controller import active_rooms, handle_game_over


class SocketIOMock:
    def __init__(self):
        self.emitted = []

    def emit(self, event, data, room=None):
        self.emitted.append({'event': event, 'data': data, 'room': room})


class TestTournamentMatchFlow(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        # Create 4 test users with Player records
        self.users = []
        for i in range(1, 5):
            u = User(username=f'player{i}', email=f'player{i}@test.com')
            u.set_password('password123')
            db.session.add(u)
            db.session.flush()
            p = Player(user_id=u.id, real_balance=100.0)
            db.session.add(p)
            self.users.append(u)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_full_tournament_match_flow(self):
        creator = self.users[0]
        # 1. Create a 4-player tournament
        t = create_tournament_record(
            creator_id=creator.id,
            tournament_type='standard',
            tournament_name='Test Championship',
            entry_fee=10.0,
            max_players=4,
        )

        # 2. Register all 4 players
        for u in self.users:
            add_tournament_participant(t.id, u.id, payment_status='completed', payment_method='wallet')
            tp = TournamentParticipant.query.filter_by(tournament_id=t.id, user_id=u.id).first()
            tp.status = 'registered'
        t.current_player_count = 4
        t.prize_pool_amount = 40.0
        db.session.commit()

        # 3. Lock tournament and build bracket
        _build_bracket(t)
        t.status = 'locked'
        db.session.commit()

        # Check semi-final matches created
        sf_brackets = TournamentBracket.query.filter_by(tournament_id=t.id, round_name='Semi-Final').all()
        self.assertEqual(len(sf_brackets), 2)

        sf1_match = TournamentMatch.query.filter_by(bracket_id=sf_brackets[0].id).first()
        self.assertIsNotNone(sf1_match)
        self.assertEqual(sf1_match.status, 'scheduled')

        # 4. Start Semi-Final Match 1 -> GameRoom creation
        match, response, code = start_tournament_match_helper(t.id, sf1_match.id, user_id=sf1_match.player1_id)
        self.assertEqual(code, 200)
        self.assertIsNotNone(match.game_room_id)
        self.assertEqual(match.status, 'in_progress')

        room = GameRoom.query.get(match.game_room_id)
        self.assertIsNotNone(room)
        self.assertEqual(room.status, 'in_progress')
        self.assertIn(room.room_code, active_rooms)

        # 5. Simulate Game Over for SF Match 1 (authoritative engine result reporting)
        mock_socket = SocketIOMock()
        handle_game_over(room, {'winner': 0, 'win_type': 'escape'}, mock_socket)

        # Verify SF Match 1 completed and winner recorded
        db.session.refresh(sf1_match)
        self.assertEqual(sf1_match.status, 'completed')
        self.assertEqual(sf1_match.winner_id, sf1_match.player1_id)
        self.assertEqual(sf1_match.loser_id, sf1_match.player2_id)

        # 6. Start & complete SF Match 2
        sf2_match = TournamentMatch.query.filter_by(bracket_id=sf_brackets[1].id).first()
        match2, resp2, code2 = start_tournament_match_helper(t.id, sf2_match.id, user_id=sf2_match.player1_id)
        self.assertEqual(code2, 200)
        room2 = GameRoom.query.get(match2.game_room_id)
        handle_game_over(room2, {'winner': 0, 'win_type': 'crazy_escape'}, mock_socket)

        db.session.refresh(sf2_match)
        self.assertEqual(sf2_match.status, 'completed')

        # Verify Final & Third-Place matches are now scheduled
        final_bracket = TournamentBracket.query.filter_by(tournament_id=t.id, round_name='Final').first()
        self.assertIsNotNone(final_bracket.match_id)
        final_match = TournamentMatch.query.get(final_bracket.match_id)
        self.assertEqual(final_match.status, 'scheduled')
        self.assertEqual(final_match.player1_id, sf1_match.winner_id)
        self.assertEqual(final_match.player2_id, sf2_match.winner_id)

        third_bracket = TournamentBracket.query.filter_by(tournament_id=t.id, round_name='Third-Place').first()
        self.assertIsNotNone(third_bracket.match_id)
        third_match = TournamentMatch.query.get(third_bracket.match_id)
        self.assertEqual(third_match.status, 'scheduled')
        self.assertEqual(third_match.player1_id, sf1_match.loser_id)
        self.assertEqual(third_match.player2_id, sf2_match.loser_id)

        # 7. Complete Third-Place Match
        match_3rd, resp_3rd, code_3rd = start_tournament_match_helper(t.id, third_match.id, user_id=third_match.player1_id)
        room_3rd = GameRoom.query.get(match_3rd.game_room_id)
        handle_game_over(room_3rd, {'winner': 0, 'win_type': 'normal'}, mock_socket)

        db.session.refresh(t)
        self.assertEqual(t.third_place_id, third_match.player1_id)

        # 8. Complete Final Match
        match_final, resp_f, code_f = start_tournament_match_helper(t.id, final_match.id, user_id=final_match.player1_id)
        room_final = GameRoom.query.get(match_final.game_room_id)
        handle_game_over(room_final, {'winner': 0, 'win_type': 'escape'}, mock_socket)

        # 9. Verify Tournament Finalization & Prize Distribution
        db.session.refresh(t)
        self.assertEqual(t.status, 'completed')
        self.assertEqual(t.winner_id, final_match.player1_id)
        self.assertEqual(t.runner_up_id, final_match.player2_id)

        prizes = TournamentPrizePool.query.filter_by(tournament_id=t.id).all()
        self.assertEqual(len(prizes), 3)
        for p in prizes:
            self.assertEqual(p.status, 'awarded')
            self.assertIsNotNone(p.user_id)


if __name__ == '__main__':
    unittest.main()
