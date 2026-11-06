"""Full-bracket announcements use the same transaction and durable outbox."""
import unittest
from datetime import datetime
from unittest.mock import patch

from app import app
from database import db, User, Tournament, TournamentParticipant, TournamentBroadcast, TournamentBracket
from controllers.tournament_controller import _build_bracket, _perform_tournament_lock
from services.tournament_broadcast_service import queue_tournament_started, process_tournament_broadcasts


class TournamentStartBroadcastTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context(); self.ctx.push()
        self.flags = {key:app.config.get(key) for key in (
            'TESTING','OPENWA_TOURNAMENT_BROADCASTS_ENABLED','OPENWA_BROADCAST_GROUP_ID','PUBLIC_APP_URL',
        )}
        app.config.update(TESTING=True,OPENWA_TOURNAMENT_BROADCASTS_ENABLED=True,
                          OPENWA_BROADCAST_GROUP_ID='test-group',PUBLIC_APP_URL='https://games.example.test/')
        db.drop_all(); db.create_all()
        users = [User(username=f'watcher{i}',email=f'watcher{i}@example.test',password_hash='unused-test-hash') for i in range(16)]
        db.session.add_all(users); db.session.flush()
        self.tournament = Tournament(tournament_code='START-TEST',tournament_name='Friday Final',
            tournament_type='standard',creator_id=users[0].id,entry_fee=10,max_players=4,
            current_player_count=4,status='open')
        db.session.add(self.tournament); db.session.flush()
        self.users = users
        for user in users[:4]:
            db.session.add(TournamentParticipant(tournament_id=self.tournament.id,user_id=user.id,
                status='registered',payment_status='completed',paid_amount=10,payment_method='wallet'))
        db.session.commit()

    def tearDown(self):
        db.session.remove(); db.drop_all(); app.config.update(self.flags); self.ctx.pop()

    def start(self):
        self.tournament.status='in_progress'; self.tournament.started_at=datetime.utcnow()
        return queue_tournament_started(self.tournament)

    def test_full_bracket_start_queues_one_announcement_with_guest_watch_link(self):
        ok, error = _perform_tournament_lock(self.tournament)
        self.assertTrue(ok,error)
        row = TournamentBroadcast.query.one()
        self.assertEqual(row.event_type,'started')
        self.assertIn('All 4 seats are filled',row.message_body)
        self.assertIn(f'https://games.example.test/tournaments/{self.tournament.id}/bracket',row.message_body)
        self.assertIn('no login required',row.message_body)
        self.assertNotIn('example.test//',row.message_body)
        _build_bracket(self.tournament)
        self.assertEqual(queue_tournament_started(self.tournament).id,row.id)
        db.session.commit()
        self.assertEqual(TournamentBroadcast.query.count(),1)

    def test_full_open_bracket_does_not_announce_before_start(self):
        self.assertIsNone(queue_tournament_started(self.tournament))
        self.assertEqual(TournamentBroadcast.query.count(),0)

    def test_partial_manual_start_does_not_claim_seats_are_full(self):
        TournamentParticipant.query.filter(TournamentParticipant.user_id.in_([self.users[2].id,self.users[3].id])).delete(synchronize_session=False)
        db.session.commit()
        self.assertTrue(_perform_tournament_lock(self.tournament)[0])
        self.assertEqual(TournamentBroadcast.query.count(),0)

    def test_pending_seat_does_not_count_as_full(self):
        participant=TournamentParticipant.query.first(); participant.status='pending'
        self.assertIsNone(self.start())
        self.assertEqual(TournamentBroadcast.query.count(),0)

    def test_promotional_start_is_clearly_labelled(self):
        self.tournament.is_promotional=True
        row=self.start()
        self.assertIn('PROMOTIONAL TOURNAMENT STARTED',row.message_body)
        self.assertIn('Friday Final',row.message_body)

    def test_full_cup_can_also_announce_its_start(self):
        self.tournament.tournament_type='cup'; self.tournament.max_players=16
        for user in self.users[4:]:
            db.session.add(TournamentParticipant(tournament_id=self.tournament.id,user_id=user.id,
                status='registered',payment_status='completed',payment_method='cup_qualification'))
        row=self.start()
        self.assertIn('All 16 seats are filled',row.message_body)

    def test_disabled_broadcast_or_missing_public_url_queues_nothing(self):
        app.config['OPENWA_TOURNAMENT_BROADCASTS_ENABLED']=False
        self.assertIsNone(self.start())
        app.config['OPENWA_TOURNAMENT_BROADCASTS_ENABLED']=True
        app.config['PUBLIC_APP_URL']=''
        self.assertIsNone(queue_tournament_started(self.tournament))
        self.assertEqual(TournamentBroadcast.query.count(),0)

    def test_failed_start_commit_rolls_back_announcement_and_brackets(self):
        with patch.object(db.session,'commit',side_effect=RuntimeError('test failed commit')):
            with self.assertRaises(RuntimeError): _build_bracket(self.tournament)
        db.session.rollback(); db.session.refresh(self.tournament)
        self.assertEqual(self.tournament.status,'open')
        self.assertEqual(TournamentBroadcast.query.count(),0)
        self.assertEqual(TournamentBracket.query.count(),0)

    def test_existing_worker_delivers_started_event_once(self):
        self.start(); db.session.commit()
        with patch('services.tournament_broadcast_service._deliver',return_value='test-message') as deliver:
            self.assertEqual(process_tournament_broadcasts(),1)
            queue_tournament_started(self.tournament); db.session.commit()
            self.assertEqual(process_tournament_broadcasts(),0)
            self.assertEqual(deliver.call_count,1)
        self.assertEqual(TournamentBroadcast.query.one().status,'sent')
