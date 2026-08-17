"""Regression tests for the tournament arena auto-start UX:

* Auto-lock: when the last seat is filled on an is_auto_lock tournament the
  join endpoint must lock the tournament and build the bracket immediately.
* Without auto-lock the tournament must stay open (no premature start).
* The lock announcement emits tournament_locked + tournament_starting so
  waiting rooms auto-redirect to the bracket.
* Joining emits participant_joined so the waiting-room player list refreshes.
"""

import unittest

from app import app
from database import (
    db, User, Player, Tournament, TournamentParticipant,
    TournamentBracket, TournamentMatch, create_tournament_record,
    add_tournament_participant,
)


class TestTournamentAutoStart(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = True
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.users = []
        for i in range(1, 5):
            u = User(username=f'player{i}', email=f'player{i}@test.com')
            u.set_password('x')
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
        with self.client.session_transaction() as s:
            s['user_id'] = user.id
            s['_fresh'] = True

    def _make_tournament(self, is_auto_lock=True):
        t = create_tournament_record(
            creator_id=self.users[0].id,
            tournament_type='standard',
            tournament_name='Auto Cup',
            entry_fee=10.0,
            max_players=4,
            is_auto_lock=is_auto_lock,
        )
        add_tournament_participant(t.id, self.users[0].id,
                                   payment_status='completed', payment_method='wallet')
        tp = TournamentParticipant.query.filter_by(
            tournament_id=t.id, user_id=self.users[0].id).first()
        tp.status = 'registered'
        tp.paid_amount = 10.0
        t.current_player_count = 1
        t.prize_pool_amount = 10.0
        db.session.commit()
        return t

    def test_auto_lock_last_join_locks_and_builds_bracket(self):
        t = self._make_tournament(is_auto_lock=True)
        for u in self.users[1:]:
            self._login(u)
            r = self.client.post(f'/api/tournaments/{t.id}/join')
            self.assertEqual(r.status_code, 200, r.get_json())
        db.session.refresh(t)
        # _build_bracket promotes the tournament to in_progress (bracket ready).
        self.assertEqual(t.status, 'in_progress')
        self.assertGreaterEqual(len(TournamentBracket.query.filter_by(
            tournament_id=t.id).all()), 2)
        self.assertGreaterEqual(len(TournamentMatch.query.filter_by(
            tournament_id=t.id).all()), 2)

    def test_no_auto_lock_stays_open_when_full(self):
        t = self._make_tournament(is_auto_lock=False)
        for u in self.users[1:]:
            self._login(u)
            r = self.client.post(f'/api/tournaments/{t.id}/join')
            self.assertEqual(r.status_code, 200, r.get_json())
        db.session.refresh(t)
        self.assertEqual(t.status, 'open')
        self.assertEqual(TournamentBracket.query.filter_by(
            tournament_id=t.id).count(), 0)

    def test_lock_announcement_emits_locked_and_starting(self):
        import controllers.tournament_controller as tc
        t = self._make_tournament(is_auto_lock=True)
        for u in self.users[1:]:
            add_tournament_participant(t.id, u.id,
                                       payment_status='completed', payment_method='wallet')
            tp = TournamentParticipant.query.filter_by(
                tournament_id=t.id, user_id=u.id).first()
            tp.status = 'registered'
            tp.paid_amount = 10.0
        t.current_player_count = 4
        t.prize_pool_amount = 40.0
        db.session.commit()

        class MockSocket:
            def __init__(self):
                self.emits = []
            def emit(self, event, data, room=None, to=None):
                self.emits.append({'event': event, 'data': data})

        mock = MockSocket()
        old = tc._socketio
        tc._socketio = mock
        try:
            ok, err = tc._perform_tournament_lock(t)
        finally:
            tc._socketio = old
        self.assertTrue(ok)
        events = {e['event'] for e in mock.emits}
        self.assertIn('tournament_locked', events)
        self.assertIn('tournament_starting', events)
        self.assertIn('tournament_updated', events)
        starting = next(e for e in mock.emits
                        if e['event'] == 'tournament_starting')
        self.assertGreater(starting['data']['countdown'], 0)

    def test_join_emits_participant_joined(self):
        import controllers.tournament_controller as tc
        t = self._make_tournament(is_auto_lock=False)

        class MockSocket:
            def __init__(self):
                self.emits = []
            def emit(self, event, data, room=None, to=None):
                self.emits.append(event)

        mock = MockSocket()
        old = tc._socketio
        tc._socketio = mock
        try:
            self._login(self.users[1])
            r = self.client.post(f'/api/tournaments/{t.id}/join')
            self.assertEqual(r.status_code, 200, r.get_json())
        finally:
            tc._socketio = old
        self.assertIn('participant_joined', mock.emits)


if __name__ == '__main__':
    unittest.main()
