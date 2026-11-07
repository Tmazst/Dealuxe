"""Regression tests for the tournament arena auto-start UX:

* Auto-lock: when the last seat is filled on an is_auto_lock tournament the
  join endpoint must lock the tournament and build the bracket immediately.
* Without auto-lock the tournament must stay open (no premature start).
* The lock announcement emits tournament_locked + tournament_starting so
  waiting rooms auto-redirect to the bracket.
* Joining emits participant_joined so the waiting-room player list refreshes.
"""

import os
from pathlib import Path
import tempfile
import unittest
import uuid

_TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / f'dealuxe-auto-start-{uuid.uuid4().hex}.db'
os.environ['DEALUXE_DATABASE_URI'] = f'sqlite:///{_TEST_DATABASE_PATH.as_posix()}'
os.environ['PILOT_MODE'] = 'false'

from app import app
from database import (
    db, User, Player, Tournament, TournamentParticipant,
    TournamentBracket, TournamentMatch, TournamentSchedule, create_tournament_record,
    add_tournament_participant,
)


class TestTournamentAutoStart(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = True
        app.config['PILOT_MODE'] = False
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
            s.clear()  # A different login must not retain the previous user's credential tag.
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

    def test_seats_filled_schedule_starts_without_separate_auto_lock_flag(self):
        t = self._make_tournament(is_auto_lock=False)
        db.session.add(TournamentSchedule(
            tournament_id=t.id,
            start_option='seats_filled',
            fallback_option='seats_filled',
        ))
        db.session.commit()

        for u in self.users[1:]:
            self._login(u)
            r = self.client.post(f'/api/tournaments/{t.id}/join')
            self.assertEqual(r.status_code, 200, r.get_json())

        db.session.refresh(t)
        self.assertEqual(t.status, 'in_progress')
        self.assertGreater(
            TournamentBracket.query.filter_by(tournament_id=t.id).count(), 0
        )

    def test_refresh_recovers_an_already_full_seats_filled_tournament(self):
        from controllers.tournament_controller import _recover_full_waiting_tournament

        t = self._make_tournament(is_auto_lock=False)
        db.session.add(TournamentSchedule(
            tournament_id=t.id,
            start_option='seats_filled',
            fallback_option='seats_filled',
        ))
        for u in self.users[1:]:
            add_tournament_participant(
                t.id, u.id, payment_status='completed', payment_method='wallet'
            )
            participant = TournamentParticipant.query.filter_by(
                tournament_id=t.id, user_id=u.id
            ).first()
            participant.status = 'registered'
        t.current_player_count = 4
        db.session.commit()

        self.assertTrue(_recover_full_waiting_tournament(t))
        db.session.refresh(t)
        self.assertEqual(t.status, 'in_progress')
        self.assertGreater(
            TournamentMatch.query.filter_by(tournament_id=t.id).count(), 0
        )

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

    def test_promotional_manual_lock_after_due_time_and_removal(self):
        self._check_eight_player_promotion_start('ordinary')

    def test_admin_start_builds_promotion_after_manual_lock(self):
        self._check_eight_player_promotion_start('start')

    def test_admin_force_start_repairs_legacy_empty_live_promotion(self):
        self._check_eight_player_promotion_start('force-start', legacy_live=True)

    def test_recovery_tool_inspects_then_repairs_empty_live_promotion(self):
        self._check_eight_player_promotion_start('recovery-tool', legacy_live=True)

    def test_reopen_preserves_entries_and_waits_for_sixteen(self):
        self._check_eight_player_promotion_start('reopen-tool', legacy_live=True)

    def test_recovery_lists_only_active_admins_without_changes(self):
        import contextlib
        import io
        from unittest.mock import patch
        from tools.recover_empty_tournament import main
        active, inactive = self.users[:2]
        active.is_admin = True
        inactive.is_admin = True
        inactive.is_active = False
        t = self._make_tournament(False)
        db.session.commit()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with patch('sys.argv', ['recover', str(t.id), '--list-admins']):
                main()
        self.assertIn(f'Administrator ID: {active.id};', output.getvalue())
        self.assertNotIn(f'Administrator ID: {inactive.id};', output.getvalue())
        db.session.refresh(t)
        self.assertEqual(t.status, 'open')
        self.assertEqual(TournamentBracket.query.filter_by(tournament_id=t.id).count(), 0)

    def _check_eight_player_promotion_start(self, start_action, legacy_live=False):
        from datetime import datetime, timedelta
        from app import socketio
        from controllers.tournament_controller import process_scheduled_events

        host = self.users[0]
        host.is_admin = True
        t = create_tournament_record(
            creator_id=host.id, tournament_type='deluxe',
            tournament_name='Evening promotion', entry_fee=10,
            max_players=16, is_auto_lock=False,
        )
        t.is_promotional = True
        t.current_player_count = 9
        t.prize_pool_amount = 90
        for index in range(9):
            user = User(username=f'promo{index}', email=f'promo{index}@test.com')
            user.set_password('x')
            db.session.add(user)
            db.session.flush()
            db.session.add(Player(user_id=user.id, real_balance=100))
            participant = add_tournament_participant(
                t.id, user.id, payment_status='completed', payment_method='wallet')
            participant.status = 'registered'
            participant.paid_amount = 10
            removed_id = user.id
        db.session.add(TournamentSchedule(
            tournament_id=t.id, start_option='custom',
            scheduled_start_at=datetime.utcnow() - timedelta(minutes=1),
            fallback_option='seats_filled',
        ))
        db.session.commit()
        process_scheduled_events()
        self.assertEqual(t.status, 'open')
        self._login(host)
        socket = socketio.test_client(app, flask_test_client=self.client)
        try:
            result = socket.emit('remove_tournament_participant', {
                'tournament_code': t.tournament_code, 'user_id': removed_id,
            }, callback=True)
            self.assertTrue(result['ok'], result)
        finally:
            socket.disconnect()
        if start_action == 'ordinary':
            start_url = f'/api/tournaments/{t.id}/lock'
        else:
            response = self.client.post(f'/api/admin/tournaments/{t.id}/lock')
            self.assertEqual(response.status_code, 200, response.get_json())
            if legacy_live:
                t.status = 'in_progress'
                t.started_at = datetime.utcnow()
                db.session.commit()
            start_url = f'/api/admin/tournaments/{t.id}/{start_action}'
        if start_action in ('recovery-tool', 'reopen-tool'):
            import contextlib
            import io
            from unittest.mock import patch
            from tools.recover_empty_tournament import main
            balances_before = {p.id: p.real_balance for p in Player.query.all()}
            with contextlib.redirect_stdout(io.StringIO()):
                with patch('sys.argv', ['recover', str(t.id)]):
                    main()
                self.assertEqual(TournamentBracket.query.filter_by(tournament_id=t.id).count(), 0)
                command = ['recover', str(t.id), '--apply', '--admin-user-id', str(host.id)]
                if start_action == 'reopen-tool':
                    command.append('--reopen')
                with patch('sys.argv', command):
                    main()
            db.session.refresh(t)  # The maintenance command uses its own app/session context.
        else:
            response = self.client.post(start_url)
            self.assertEqual(response.status_code, 200, response.get_json())
        if start_action == 'reopen-tool':
            self.assertEqual({p.id: p.real_balance for p in Player.query.all()}, balances_before)
            self.assertTrue(t.is_promotional)
            self.assertFalse(t.promotional_wallet_payouts)
            self.assertEqual(t.status, 'open')
            self.assertEqual(t.current_player_count, 8)
            self.assertIsNone(t.started_at)
            self.assertIsNone(t.locked_at)
            self.assertIsNone(t.locked_player_count)
            self.assertFalse(t.is_auto_lock)
            self.assertEqual(t.schedule.start_option, 'seats_filled')
            self.assertIsNone(t.schedule.scheduled_start_at)
            self.assertEqual(TournamentParticipant.query.filter_by(
                tournament_id=t.id, status='registered', payment_status='completed').count(), 8)
            self.assertEqual(TournamentParticipant.query.filter_by(
                tournament_id=t.id, user_id=removed_id).first().status, 'withdrawn')
            process_scheduled_events()
            self.assertEqual(t.status, 'open')
            self.assertEqual(TournamentBracket.query.filter_by(tournament_id=t.id).count(), 0)
            for index in range(8):
                user = User(username=f'newjoin{index}', email=f'newjoin{index}@test.com', password_hash='test')
                db.session.add(user)
                db.session.flush()
                db.session.add(Player(user_id=user.id, real_balance=100))
                db.session.commit()
                self._login(user)
                response = self.client.post(f'/api/tournaments/{t.id}/join')
                self.assertEqual(response.status_code, 200, response.get_json())
                db.session.refresh(t)
                self.assertEqual(t.status, 'open' if index < 7 else 'in_progress')
            self.assertEqual(t.locked_player_count, 16)
            self.assertEqual(TournamentMatch.query.filter_by(tournament_id=t.id).count(), 8)
            from admin.service import reopen_empty_tournament
            with self.assertRaisesRegex(ValueError, 'existing bracket'):
                reopen_empty_tournament(t.id, host.id)
            self.assertEqual(TournamentMatch.query.filter_by(tournament_id=t.id).count(), 8)
            return
        overview = self.client.get(f'/api/tournaments/{t.id}/overview').get_json()
        self.assertEqual(overview['tournament']['status'], 'in_progress')
        matches = overview['matches']
        self.assertEqual(len(matches), 4)
        paired_ids = [m[key] for m in matches for key in ('player1_id', 'player2_id')]
        self.assertEqual(len(set(paired_ids)), 8)
        self.assertNotIn(host.id, paired_ids)
        self.assertNotIn(removed_id, paired_ids)
        self.assertTrue(all(m['status'] == 'scheduled' for m in matches))
        self.assertEqual(t.locked_player_count, 8)
        if start_action not in ('ordinary', 'recovery-tool'):
            response = self.client.post(start_url)
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(TournamentMatch.query.filter_by(tournament_id=t.id).count(), 4)

    def test_admin_start_rejects_insufficient_players_and_terminal_tournaments(self):
        host = self.users[0]
        host.is_admin = True
        t = self._make_tournament(False)
        db.session.commit()
        self._login(host)
        for action in ('start', 'force-start'):
            response = self.client.post(f'/api/admin/tournaments/{t.id}/{action}')
            self.assertEqual(response.status_code, 400, response.get_json())
            db.session.refresh(t)
            self.assertEqual(t.status, 'open')
        for status in ('completed', 'cancelled'):
            t.status = status
            db.session.commit()
            for action in ('start', 'force-start'):
                response = self.client.post(f'/api/admin/tournaments/{t.id}/{action}')
                self.assertEqual(response.status_code, 400)
                db.session.refresh(t)
                self.assertEqual(t.status, status)


if __name__ == '__main__':
    unittest.main()
