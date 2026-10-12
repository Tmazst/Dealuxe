"""Allocated empty-Cup workflow tests using a disposable database."""

import os
from pathlib import Path
import tempfile
import unittest
import uuid


_DB_PATH = Path(tempfile.gettempdir()) / 'dealuxe-cup-alloc-{0}.db'.format(
    uuid.uuid4().hex
)
os.environ['ENV'] = 'testing'
os.environ['DEALUXE_DATABASE_URI'] = 'sqlite:///{0}'.format(_DB_PATH.as_posix())
os.environ['CSRF_SECURITY_MODE'] = 'off'
os.environ['REQUEST_SECURITY_MODE'] = 'off'
os.environ['MOJAPOS_MOCK_MODE'] = 'true'

from app import app
from admin.service import (
    assign_manual_cup_seat,
    create_cup_tournament,
    start_allocated_cup,
    update_cup_allocations,
)
from database import (
    AdminAuditLog,
    CupQualification,
    Player,
    Tournament,
    TournamentBracket,
    TournamentParticipant,
    User,
    create_tournament_record,
    db,
)
from services.cup_qualification_service import award_cup_qualification


class AllocatedCupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = app.app_context()
        cls.context.push()
        app.config.update(
            TESTING=True,
            CUP_ENABLED=True,
            CUP_CASH_PAYOUTS_ENABLED=False,
            CUP_REQUIRE_CHECK_IN_TO_START=False,
            CUP_EVENT_KEY='allocated-cup-test',
            CUP_SEASON='2026',
            CUP_ALLOWED_CAPACITIES=(16, 32, 64),
            CUP_DEFAULT_CAPACITY=16,
        )

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.context.pop()
        try:
            _DB_PATH.unlink(missing_ok=True)
        except PermissionError:
            pass

    def setUp(self):
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        self.admin = self._user('allocation_admin', admin=True)
        db.session.commit()

    def tearDown(self):
        db.session.remove()

    def _user(self, username, admin=False):
        user = User(
            username=username,
            email='{0}@example.test'.format(username),
            is_admin=admin,
            is_active=True,
        )
        user.set_password('test-password')
        db.session.add(user)
        db.session.flush()
        db.session.add(Player(user_id=user.id))
        return user

    def _empty_cup(self, testing=10, sponsor=2, invite=1):
        return create_cup_tournament(
            self.admin.id,
            tournament_name='Allocated Pilot Cup',
            capacity=16,
            creation_mode='empty',
            seat_allocations={
                'testing': testing,
                'sponsor': sponsor,
                'admin_invite': invite,
            },
        )

    def test_empty_cup_persists_predefined_allocations(self):
        result = self._empty_cup()
        cup = db.session.get(Tournament, result['tournament_id'])

        self.assertEqual(cup.status, 'open')
        self.assertEqual(cup.current_player_count, 0)
        self.assertEqual(result['allocations'], {
            'bracket_winner': 3,
            'admin_invite': 1,
            'sponsor': 2,
            'testing': 10,
        })
        self.assertEqual(TournamentBracket.query.count(), 0)

    def test_manual_and_bracket_winner_seats_obey_allocations(self):
        cup_result = self._empty_cup(testing=1, sponsor=1, invite=1)
        cup_id = cup_result['tournament_id']
        tester = self._user('tester_one')
        sponsor = self._user('sponsor_one')
        invitee = self._user('invitee_one')
        winner = self._user('winner_one')
        db.session.commit()

        assign_manual_cup_seat(
            cup_id, tester.id, 'testing', 'Rehearsal seat', self.admin.id
        )
        assign_manual_cup_seat(
            cup_id, sponsor.id, 'sponsor', 'Sponsor entitlement',
            self.admin.id, 'Business ABC',
        )
        assign_manual_cup_seat(
            cup_id, invitee.id, 'admin_invite', 'Community invitation', self.admin.id
        )
        source = create_tournament_record(
            creator_id=winner.id, tournament_type='standard',
            tournament_name='Qualifier', entry_fee=0, max_players=4,
        )
        qualification, awarded = award_cup_qualification(
            source, winner.id, 'allocated-cup-test', '2026', capacity=16
        )
        db.session.commit()

        self.assertTrue(awarded)
        self.assertEqual(qualification.target_cup_tournament_id, cup_id)
        self.assertEqual(qualification.seat_source, 'bracket_winner')
        self.assertEqual(
            TournamentParticipant.query.filter_by(tournament_id=cup_id).count(), 4
        )
        with self.assertRaisesRegex(ValueError, 'allocation is full'):
            assign_manual_cup_seat(
                cup_id, self._user('tester_two').id, 'testing',
                'Extra test seat', self.admin.id,
            )
        self.assertIsNotNone(AdminAuditLog.query.filter_by(
            action='cup_seat.assign_manual'
        ).first())

    def test_full_testing_cup_starts_only_after_all_64_manual_seats(self):
        result = create_cup_tournament(
            self.admin.id, tournament_name='64 Tester Rehearsal', capacity=64,
            creation_mode='empty', seat_allocations={'testing': 64},
        )
        cup_id = result['tournament_id']
        for index in range(64):
            user = self._user('tester_{0:02d}'.format(index))
            db.session.flush()
            assign_manual_cup_seat(
                cup_id, user.id, 'testing', 'Full rehearsal roster', self.admin.id
            )

        started = start_allocated_cup(cup_id, self.admin.id)
        cup = db.session.get(Tournament, cup_id)
        self.assertEqual(started['players'], 64)
        self.assertEqual(cup.status, 'in_progress')
        self.assertEqual(
            TournamentBracket.query.filter_by(
                tournament_id=cup_id, round_number=1
            ).count(),
            32,
        )

    def test_reallocation_is_audited_and_cannot_undercut_occupied_seats(self):
        result = self._empty_cup(testing=2, sponsor=1, invite=0)
        cup_id = result['tournament_id']
        tester = self._user('occupied_tester')
        db.session.commit()
        assign_manual_cup_seat(
            cup_id, tester.id, 'testing', 'Initial rehearsal seat', self.admin.id
        )
        with self.assertRaisesRegex(ValueError, 'occupied seats'):
            update_cup_allocations(
                cup_id,
                {'testing': 0, 'sponsor': 1, 'admin_invite': 0},
                self.admin.id,
                'Reduce testing seats',
            )
        updated = update_cup_allocations(
            cup_id,
            {'testing': 1, 'sponsor': 2, 'admin_invite': 0},
            self.admin.id,
            'Move one unused testing seat to sponsor allocation',
        )
        self.assertEqual(updated['allocations']['testing'], 1)
        self.assertEqual(updated['allocations']['sponsor'], 2)
        self.assertIsNotNone(AdminAuditLog.query.filter_by(
            action='cup_seat.reallocate'
        ).first())


if __name__ == '__main__':
    unittest.main()
