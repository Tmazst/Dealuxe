"""Cup public-page regression tests using an explicitly disposable database."""

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid


_TEST_DATABASE_PATH = (
    Path(tempfile.gettempdir())
    / 'dealuxe-cup-public-{0}_test.db'.format(uuid.uuid4().hex)
)
os.environ['ENV'] = 'testing'
os.environ['DEALUXE_DATABASE_URI'] = (
    'sqlite:///{0}'.format(_TEST_DATABASE_PATH.as_posix())
)
os.environ['CSRF_SECURITY_MODE'] = 'off'
os.environ['REQUEST_SECURITY_MODE'] = 'off'
os.environ['MOJAPOS_MOCK_MODE'] = 'true'

from app import app
from controllers.tournament_controller import _serialize_tournament
from database import (
    Player,
    Tournament,
    TournamentParticipant,
    User,
    create_tournament_record,
    db,
)


class CupPublicExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_context = app.app_context()
        cls.app_context.push()
        app.config.update(
            TESTING=True,
            CSRF_SECURITY_MODE='off',
            REQUEST_SECURITY_MODE='off',
        )

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.app_context.pop()
        try:
            _TEST_DATABASE_PATH.unlink(missing_ok=True)
        except PermissionError:
            # A Windows background-scheduler handle may close just after the
            # test process exits; the file is uniquely named and disposable.
            pass

    def setUp(self):
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

        self.admin = User(
            username='cup_admin',
            email='cup-admin@example.test',
            phone='+26876000001',
            is_admin=True,
            is_super_admin=True,
        )
        self.admin.set_password('test-password')
        self.player = User(
            username='Opera',
            email='opera-private@example.test',
            phone='+26876000002',
        )
        self.player.set_password('test-password')
        db.session.add_all([self.admin, self.player])
        db.session.flush()
        db.session.add_all([
            Player(user_id=self.admin.id),
            Player(user_id=self.player.id),
        ])

        self.cup = create_tournament_record(
            creator_id=self.admin.id,
            tournament_type='cup',
            tournament_name='uMshova Pilot Cup',
            entry_fee=0,
            max_players=16,
            is_auto_lock=True,
            locked_player_count=16,
        )
        self.cup.status = 'in_progress'
        self.cup.current_player_count = 16
        self.cup.notes = json.dumps({
            'event_key': 'umshova-cup-pilot',
            'season': '2026',
        })
        self.cup.event_start_at = datetime(2026, 11, 14, 10, 0)
        self.cup.event_check_in_at = datetime(2026, 11, 14, 9, 0)
        self.cup.event_venue_name = 'Botho University Hall'
        self.cup.event_venue_address = 'Main Campus, Manzini'
        self.cup.event_public_notes = 'Bring a charged phone and arrive early.'
        db.session.add(TournamentParticipant(
            tournament_id=self.cup.id,
            user_id=self.player.id,
            status='registered',
            payment_status='completed',
        ))

        self.ordinary = create_tournament_record(
            creator_id=self.player.id,
            tournament_type='standard',
            tournament_name='Ordinary Four',
            entry_fee=10,
            max_players=4,
        )
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()

    def _login_as_admin(self):
        with self.client.session_transaction() as session:
            session['user_id'] = self.admin.id
            session['_fresh'] = True

    def test_arena_has_separate_cup_and_ordinary_sections(self):
        response = self.client.get('/tournaments')
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Tournament Cups', body)
        self.assertIn('id="cups-grid"', body)
        self.assertIn('Tournament brackets', body)
        self.assertIn("tournament.type !== 'cup'", body)

    def test_legacy_cup_details_url_redirects_to_dedicated_page(self):
        response = self.client.get('/tournaments/{0}'.format(self.cup.id))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith(
            '/cups/{0}'.format(self.cup.id)
        ))

    def test_cup_page_shows_event_and_roster_without_contact_details(self):
        response = self.client.get('/cups/{0}'.format(self.cup.id))
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('uMshova Pilot Cup', body)
        self.assertIn('Botho University Hall', body)
        self.assertIn('Main Campus, Manzini', body)
        self.assertIn('Opera', body)
        self.assertIn('View Cup bracket', body)
        self.assertNotIn(self.player.email, body)
        self.assertNotIn(self.player.phone, body)
        self.assertNotIn('Waiting for players', body)

    def test_public_serializer_contains_contact_free_event_metadata(self):
        payload = _serialize_tournament(self.cup)
        self.assertEqual(payload['type'], 'cup')
        self.assertEqual(payload['event']['venue_name'], 'Botho University Hall')
        serialized = json.dumps(payload)
        self.assertNotIn(self.player.email, serialized)
        self.assertNotIn(self.player.phone, serialized)

        response_payload = self.client.get('/api/tournaments').get_json()
        public_cup = next(
            item for item in response_payload['tournaments']
            if item['id'] == self.cup.id
        )
        self.assertEqual(public_cup['event']['season'], '2026')

    def test_unpublished_event_details_fail_closed_to_announcement_copy(self):
        self.cup.event_start_at = None
        self.cup.event_check_in_at = None
        self.cup.event_venue_name = None
        self.cup.event_venue_address = None
        db.session.commit()
        body = self.client.get(
            '/cups/{0}'.format(self.cup.id)
        ).get_data(as_text=True)
        self.assertIn('To be announced', body)
        self.assertNotIn(self.player.email, body)

    def test_payment_callback_route_remains_registered(self):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        self.assertIn('/api/payment/callback', rules)
        response = self.client.post('/api/payment/callback', json={})
        self.assertNotEqual(response.status_code, 404)

    def test_admin_can_update_public_details_and_invalid_time_is_rejected(self):
        self._login_as_admin()
        response = self.client.patch(
            '/api/admin/cup-tournaments/{0}/event-details'.format(self.cup.id),
            json={
                'tournament_name': 'uMshova Cup Manzini',
                'event_start_at': '2026-12-05T11:00',
                'event_check_in_at': '2026-12-05T09:30',
                'event_venue_name': 'Manzini Library Hall',
                'event_venue_address': 'Manzini Library',
                'event_public_notes': 'Registration closes at 09:45.',
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        db.session.refresh(self.cup)
        self.assertEqual(self.cup.tournament_name, 'uMshova Cup Manzini')
        self.assertEqual(self.cup.event_venue_name, 'Manzini Library Hall')

        invalid = self.client.patch(
            '/api/admin/cup-tournaments/{0}/event-details'.format(self.cup.id),
            json={
                'tournament_name': 'uMshova Cup Manzini',
                'event_start_at': '2026-12-05T10:00',
                'event_check_in_at': '2026-12-05T11:00',
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('cannot be after', invalid.get_json()['error'])

    def test_non_admin_cannot_edit_cup_event_details(self):
        with self.client.session_transaction() as session:
            session['user_id'] = self.player.id
        response = self.client.patch(
            '/api/admin/cup-tournaments/{0}/event-details'.format(self.cup.id),
            json={'event_venue_name': 'Not allowed'},
        )
        self.assertEqual(response.status_code, 403)

    def test_ordinary_tournament_still_uses_waiting_room(self):
        response = self.client.get('/tournaments/{0}'.format(self.ordinary.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(self.ordinary.id), response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
