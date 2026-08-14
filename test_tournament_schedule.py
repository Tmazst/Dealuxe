import os
import unittest
from datetime import datetime, timedelta

os.environ['ENV'] = 'development'

from app import app
from database import (
    db,
    User,
    Player,
    Tournament,
    TournamentBracket,
    TournamentParticipant,
    TournamentMatch,
    TournamentSchedule,
    MatchRoll,
    create_tournament_record,
    add_tournament_participant,
)
from controllers.tournament_controller import (
    _build_bracket,
    process_scheduled_events,
)


class TestTournamentSchedulingAndRoll(unittest.TestCase):
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

    def _create(self, start_option='seats_filled', custom_time_str=None):
        self._login(self.users[0])
        r = self.client.post('/api/tournaments/create', json={
            'tournament_type': 'standard',
            'tournament_name': 'Sched Cup',
            'is_auto_lock': False,
            'start_option': start_option,
            'custom_time_str': custom_time_str,
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()['tournament']['id']

    def test_schedule_seats_filled(self):
        tid = self._create('seats_filled')
        schedule = TournamentSchedule.query.filter_by(tournament_id=tid).first()
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule.start_option, 'seats_filled')
        self.assertIsNone(schedule.scheduled_start_at)

    def test_schedule_countdown(self):
        tid = self._create('in_10min')
        schedule = TournamentSchedule.query.filter_by(tournament_id=tid).first()
        self.assertEqual(schedule.start_option, 'in_10min')
        expected = datetime.utcnow() + timedelta(minutes=10)
        self.assertLess(abs((schedule.scheduled_start_at - expected).total_seconds()), 60)

    def test_schedule_custom_time(self):
        tid = self._create('custom', '13:30')
        schedule = TournamentSchedule.query.filter_by(tournament_id=tid).first()
        self.assertEqual(schedule.start_option, 'custom')
        self.assertEqual(schedule.custom_time_str, '13:30')
        # Always within the next 24 hours
        now = datetime.utcnow()
        delay = schedule.scheduled_start_at - now
        self.assertGreater(delay, timedelta(0))
        self.assertLess(delay, timedelta(hours=24))

    def test_schedule_invalid_inputs(self):
        self._login(self.users[0])
        r = self.client.post('/api/tournaments/create', json={
            'tournament_type': 'standard', 'start_option': 'custom', 'custom_time_str': 'not-a-time',
        })
        self.assertEqual(r.status_code, 400)

        r = self.client.post('/api/tournaments/create', json={
            'tournament_type': 'standard', 'start_option': 'bogus',
        })
        self.assertEqual(r.status_code, 400)

    def test_serialization_includes_schedule(self):
        tid = self._create('in_5min')
        self._login(self.users[0])
        r = self.client.get('/api/tournaments')
        arena = next(x for x in r.get_json()['tournaments'] if x['id'] == tid)
        self.assertEqual(arena['schedule']['start_option'], 'in_5min')
        self.assertIsNotNone(arena['schedule']['scheduled_start_at'])
        self.assertIn('scheduled', arena['schedule_message'].lower())

    def test_join_includes_schedule_message(self):
        tid = self._create('in_20min')
        self._login(self.users[1])
        r = self.client.post(f'/api/tournaments/{tid}/join')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('tournament_message', data)
        self.assertIn('scheduled', data['tournament_message'].lower())

    def test_fallback_to_seats_filled_when_not_full(self):
        tid = self._create('in_10min')
        with self.app_context:
            schedule = TournamentSchedule.query.filter_by(tournament_id=tid).first()
            schedule.scheduled_start_at = datetime.utcnow() - timedelta(minutes=1)
            db.session.commit()

        process_scheduled_events()

        with self.app_context:
            tournament = Tournament.query.get(tid)
            schedule = TournamentSchedule.query.filter_by(tournament_id=tid).first()
            # Fallback: stays open, waits for seats
            self.assertEqual(tournament.status, 'open')
            self.assertEqual(schedule.start_option, 'seats_filled')
            self.assertIsNone(schedule.scheduled_start_at)

    def test_scheduled_start_locks_when_full(self):
        tid = self._create('in_5min')
        with self.app_context:
            for u in self.users[1:4]:
                add_tournament_participant(tid, u.id, payment_status='completed', payment_method='wallet')
                tp = TournamentParticipant.query.filter_by(tournament_id=tid, user_id=u.id).first()
                tp.status = 'registered'
            t = Tournament.query.get(tid)
            t.current_player_count = 4
            t.prize_pool_amount = 40.0
            schedule = TournamentSchedule.query.filter_by(tournament_id=tid).first()
            schedule.scheduled_start_at = datetime.utcnow() - timedelta(minutes=1)
            db.session.commit()

        process_scheduled_events()

        with self.app_context:
            tournament = Tournament.query.get(tid)
            self.assertIn(tournament.status, ('locked', 'in_progress'))
            brackets = TournamentBracket.query.filter_by(tournament_id=tid).count()
            self.assertGreater(brackets, 0)

    def _build_full_tournament(self):
        """Create a locked 4-player tournament and return (tid, match_id, p1, p2)."""
        tid = self._create('seats_filled')
        with self.app_context:
            for u in self.users[1:4]:
                add_tournament_participant(tid, u.id, payment_status='completed', payment_method='wallet')
                tp = TournamentParticipant.query.filter_by(tournament_id=tid, user_id=u.id).first()
                tp.status = 'registered'
            t = Tournament.query.get(tid)
            t.current_player_count = 4
            t.prize_pool_amount = 40.0
            _build_bracket(t)
            t.status = 'locked'
            db.session.commit()
            match = TournamentMatch.query.filter_by(tournament_id=tid).first()
            return tid, match.id, match.player1_id, match.player2_id

    def test_roll_game_lifecycle(self):
        tid, match_id, p1, p2 = self._build_full_tournament()

        # Non-participant cannot roll
        other = next(u for u in self.users if u.id not in (p1, p2))
        self._login(other)
        r = self.client.post(f'/api/tournaments/{tid}/matches/{match_id}/roll')
        self.assertEqual(r.status_code, 403)

        # Participant rolls
        self._login(next(u for u in self.users if u.id == p1))
        r = self.client.post(f'/api/tournaments/{tid}/matches/{match_id}/roll')
        self.assertEqual(r.status_code, 200, r.get_json())
        roll = MatchRoll.query.filter_by(match_id=match_id, status='rolling').first()
        self.assertIsNotNone(roll)
        self.assertEqual(roll.requested_by, p1)
        expected_deadline = datetime.utcnow() + timedelta(seconds=600)
        self.assertLess(abs((roll.deadline - expected_deadline).total_seconds()), 60)

        # Expire the deadline and process
        with self.app_context:
            roll = MatchRoll.query.filter_by(match_id=match_id, status='rolling').first()
            roll.deadline = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

        process_scheduled_events()

        with self.app_context:
            match = TournamentMatch.query.get(match_id)
            self.assertEqual(match.status, 'completed')
            self.assertEqual(match.winner_id, p1)
            self.assertEqual(match.loser_id, p2)
            self.assertEqual(match.win_type, 'no_show')
            roll = MatchRoll.query.filter_by(match_id=match_id).first()
            self.assertEqual(roll.status, 'resolved')
            self.assertEqual(roll.winner_id, p1)

    def test_roll_rejected_when_opponent_connected(self):
        tid, match_id, p1, p2 = self._build_full_tournament()
        with self.app_context:
            from controllers.tournament_controller import start_tournament_match_helper
            from database import GameRoom
            match, _resp, code = start_tournament_match_helper(tid, match_id, user_id=p1)
            self.assertEqual(code, 200)
            room = GameRoom.query.get(match.game_room_id)
            room.player2_connected = True
            db.session.commit()

        self._login(next(u for u in self.users if u.id == p1))
        r = self.client.post(f'/api/tournaments/{tid}/matches/{match_id}/roll')
        self.assertEqual(r.status_code, 400)
        self.assertIn('online', r.get_json()['error'])


if __name__ == '__main__':
    unittest.main()

