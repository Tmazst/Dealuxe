import os
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import (
    db,
    User,
    Player,
    Tournament,
    Transaction,
    TX_WALLET_TOPUP,
    AdminAuditLog,
    Dispute,
    WalletAdjustment,
    CupQualification,
    create_tournament_record,
    add_tournament_participant,
    get_player_by_user_id,
)


class TestAdminExpansion(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = 'true'
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.admin = User(username='boss', email='boss@test.com', is_admin=True)
        self.admin.set_password('pw')
        db.session.add(self.admin)
        db.session.flush()
        db.session.add(Player(user_id=self.admin.id, real_balance=100.0))

        self.regular = User(username='player1', email='p1@test.com')
        self.regular.set_password('pw')
        db.session.add(self.regular)
        db.session.flush()
        db.session.add(Player(user_id=self.regular.id, real_balance=50.0, fake_balance=10.0))
        db.session.commit()

        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post('/api/auth/login', json={'username': user.username, 'password': 'pw'})

    def test_admin_endpoints_require_admin(self):
        self._login(self.regular)
        r = self.client.get('/api/admin/users')
        self.assertEqual(r.status_code, 403)
        r = self.client.get('/api/admin/audit-logs')
        self.assertEqual(r.status_code, 403)
        r = self.client.get('/api/admin/cup-qualifications')
        self.assertEqual(r.status_code, 403)

    def _seed_cup_roster(self):
        candidate = User(username='reserve1', email='reserve1@test.com')
        candidate.set_password('pw')
        db.session.add(candidate)
        db.session.flush()
        db.session.add(Player(user_id=candidate.id))

        first = create_tournament_record(
            creator_id=self.regular.id,
            tournament_type='standard',
            tournament_name='Qualifier One',
            entry_fee=10.0,
            max_players=4,
        )
        second = create_tournament_record(
            creator_id=candidate.id,
            tournament_type='standard',
            tournament_name='Qualifier Two',
            entry_fee=10.0,
            max_players=4,
        )
        event_key = app.config['CUP_EVENT_KEY']
        active = CupQualification(
            source_tournament_id=first.id,
            user_id=self.regular.id,
            season='2026',
            event_key=event_key,
            status='qualified',
            seat_key=f'{event_key}:{self.regular.id}',
        )
        reserve = CupQualification(
            source_tournament_id=second.id,
            user_id=candidate.id,
            season='2026',
            event_key=event_key,
            status='reserve',
        )
        db.session.add_all([active, reserve])
        db.session.commit()
        return active.id, reserve.id, candidate.id

    def test_cup_roster_check_in_and_replacement_are_audited(self):
        active_id, reserve_id, candidate_id = self._seed_cup_roster()
        self._login(self.admin)

        roster = self.client.get('/api/admin/cup-qualifications')
        self.assertEqual(roster.status_code, 200)
        payload = roster.get_json()
        self.assertEqual(payload['active_seats'], 1)
        self.assertEqual(payload['capacity'], 64)
        self.assertEqual(payload['remaining_seats'], 63)
        admin_page = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('uMshova Cup Qualification Roster', admin_page)

        checked_in = self.client.post(
            f'/api/admin/cup-qualifications/{active_id}/check-in'
        )
        self.assertEqual(checked_in.status_code, 200)
        self.assertEqual(
            checked_in.get_json()['qualification']['status'], 'checked_in'
        )

        replaced = self.client.post(
            f'/api/admin/cup-qualifications/{active_id}/replace',
            json={
                'replacement_qualification_id': reserve_id,
                'reason': 'Original qualifier unavailable for Cup day',
            },
        )
        self.assertEqual(replaced.status_code, 200, replaced.get_json())
        self.assertEqual(replaced.get_json()['replaced']['status'], 'replaced')
        self.assertEqual(replaced.get_json()['replacement']['status'], 'qualified')

        replacement = CupQualification.query.get(reserve_id)
        self.assertEqual(replacement.user_id, candidate_id)
        self.assertTrue(replacement.seat_key)
        self.assertEqual(replacement.replacement_for_id, active_id)
        self.assertEqual(CupQualification.query.filter(
            CupQualification.status.in_(('qualified', 'checked_in'))
        ).count(), 1)
        actions = {
            log.action for log in AdminAuditLog.query.filter(
                AdminAuditLog.entity_type == 'cup_qualification'
            ).all()
        }
        self.assertIn('cup_qualification.check_in', actions)
        self.assertIn('cup_qualification.replace', actions)

    def test_cup_roster_reserve_and_revoke_require_reasons(self):
        active_id, _, _ = self._seed_cup_roster()
        self._login(self.admin)

        missing_reason = self.client.post(
            f'/api/admin/cup-qualifications/{active_id}/reserve', json={}
        )
        self.assertEqual(missing_reason.status_code, 400)

        reserve = self.client.post(
            f'/api/admin/cup-qualifications/{active_id}/reserve',
            json={'reason': 'Awaiting attendance confirmation'},
        )
        self.assertEqual(reserve.status_code, 200)
        self.assertEqual(reserve.get_json()['qualification']['status'], 'reserve')

        revoke = self.client.post(
            f'/api/admin/cup-qualifications/{active_id}/revoke',
            json={'reason': 'Player withdrew'},
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertEqual(revoke.get_json()['qualification']['status'], 'revoked')

    def test_user_activity_requires_admin(self):
        self._login(self.regular)
        r = self.client.get(f'/api/admin/users/{self.admin.id}/activity')
        self.assertEqual(r.status_code, 403)

    def test_user_activity_returns_ledger_and_audit(self):
        self._login(self.admin)
        # A wallet adjustment records an audit entry for the user.
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': 25.0,
            'reason': 'Goodwill credit',
        })
        self.assertEqual(r.status_code, 200)

        # A financial transaction row on the user's player ledger.
        player = get_player_by_user_id(self.regular.id)
        tx = Transaction(
            player_id=player.id,
            transaction_type=TX_WALLET_TOPUP,
            amount=25.0,
            balance_type='real',
            balance_before=50.0,
            balance_after=75.0,
            description='Test topup',
            status='completed',
        )
        db.session.add(tx)
        db.session.commit()

        r = self.client.get(f'/api/admin/users/{self.regular.id}/activity')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data['user']['username'], 'player1')
        self.assertEqual(len(data['transactions']), 1)
        self.assertEqual(data['transactions'][0]['transaction_type'], 'wallet_topup')
        self.assertTrue(any(log['action'] == 'wallet.adjust' for log in data['audit_logs']))

    def test_user_activity_unknown_user_404(self):
        self._login(self.admin)
        r = self.client.get('/api/admin/users/999999/activity')
        self.assertEqual(r.status_code, 404)

    def test_backend_logs_requires_admin(self):
        self._login(self.regular)
        r = self.client.get('/api/admin/logs')
        self.assertEqual(r.status_code, 403)

    def test_backend_logs_endpoint(self):
        self._login(self.admin)
        r = self.client.get('/api/admin/logs?tail=50&search=PAYMENT')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('lines', data)
        self.assertIn('log_file', data)
        self.assertIsInstance(data['lines'], list)

    def test_backend_logs_clear(self):
        self._login(self.admin)
        r = self.client.post('/api/admin/logs/clear')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get('cleared'))

    def test_wallet_adjust_credits_and_audits(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': 25.0,
            'reason': 'Tournament refund adjustment',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['wallet']['new_balance'], 75.0)

        # Balance persisted
        player = get_player_by_user_id(self.regular.id)
        self.assertEqual(player.real_balance, 75.0)

        # Wallet adjustment row logged
        adj = WalletAdjustment.query.filter_by(user_id=self.regular.id).first()
        self.assertIsNotNone(adj)
        self.assertEqual(adj.delta, 25.0)
        self.assertEqual(adj.reason, 'Tournament refund adjustment')

        # Audit log entry recorded
        log = AdminAuditLog.query.filter_by(action='wallet.adjust').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.admin_user_id, self.admin.id)
        self.assertEqual(log.entity_id, self.regular.id)

    def test_wallet_adjust_rejects_negative_balance(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': -500.0,
            'reason': 'Clawback',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('negative', r.get_json()['error'])

    def test_wallet_adjust_requires_reason(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'fake',
            'delta': 10.0,
        })
        self.assertEqual(r.status_code, 400)

    def test_award_credits(self):
        self._login(self.admin)
        r = self.client.post(f'/api/admin/users/{self.regular.id}/credits', json={
            'amount': 500,
            'balance_type': 'fake',
            'reason': 'Promotional pack',
        })
        self.assertEqual(r.status_code, 200)
        player = get_player_by_user_id(self.regular.id)
        self.assertEqual(player.fake_balance, 510.0)

    def test_dispute_workflow(self):
        # Player files a dispute (login required, not admin-only)
        self._login(self.regular)
        r = self.client.post('/api/admin/disputes', json={
            'category': 'payment',
            'description': 'Entry fee charged twice',
        })
        self.assertEqual(r.status_code, 201)
        dispute = r.get_json()['dispute']
        self.assertEqual(dispute['status'], 'pending')

        # Admin lists disputes
        self._login(self.admin)
        r = self.client.get('/api/admin/disputes')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()['disputes']), 1)

        # Admin resolves
        r = self.client.post(f"/api/admin/disputes/{dispute['id']}/resolve", json={
            'status': 'resolved',
            'resolution': 'Refunded second charge',
        })
        self.assertEqual(r.status_code, 200)
        resolved = r.get_json()['dispute']
        self.assertEqual(resolved['status'], 'resolved')
        self.assertEqual(resolved['resolved_by'], self.admin.id)

        # Audit logged
        log = AdminAuditLog.query.filter_by(action='dispute.resolved').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.entity_id, dispute['id'])

    def test_audit_logs_endpoint(self):
        self._login(self.admin)
        self.client.post(f'/api/admin/wallets/{self.regular.id}/adjust', json={
            'balance_type': 'real',
            'delta': 5.0,
            'reason': 'Goodwill credit',
        })
        r = self.client.get('/api/admin/audit-logs')
        self.assertEqual(r.status_code, 200)
        logs = r.get_json()['logs']
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]['action'], 'wallet.adjust')
        self.assertEqual(logs[0]['admin_username'], 'boss')

    def test_tournament_force_start_and_complete(self):
        self._login(self.admin)
        with app.app_context():
            t = create_tournament_record(
                creator_id=self.regular.id, tournament_type='standard',
                tournament_name='Admin Cup', entry_fee=10.0, max_players=4,
            )
            for u in (self.admin, self.regular):
                add_tournament_participant(t.id, u.id, payment_status='completed', payment_method='wallet')
            db.session.commit()
            tid = t.id

        # Force-start builds the bracket and moves to in_progress
        r = self.client.post(f'/api/admin/tournaments/{tid}/force-start')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'in_progress')

        # Detail endpoint returns fixtures
        r = self.client.get(f'/api/admin/tournaments/{tid}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('fixtures', r.get_json())
        self.assertIn('participants', r.get_json())

        # Force-complete
        r = self.client.post(f'/api/admin/tournaments/{tid}/complete')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'completed')

    def test_patch_rejects_admin_role_change(self):
        self._login(self.admin)
        # is_admin can no longer be set through the API (super admin CLI only)
        r = self.client.patch(f'/api/admin/users/{self.regular.id}', json={'is_admin': True})
        self.assertEqual(r.status_code, 400)
        self.assertIn('super admin CLI', r.get_json()['error'])

        # The role was NOT changed
        with self.app_context:
            user = User.query.get(self.regular.id)
            self.assertFalse(user.is_admin)

    def test_super_admin_can_access_admin_endpoints(self):
        with self.app_context:
            super_admin = User(username='god', email='god@test.com', is_super_admin=True)
            super_admin.set_password('pw')
            db.session.add(super_admin)
            db.session.flush()
            db.session.add(Player(user_id=super_admin.id))
            db.session.commit()

        # Log in as the super admin directly
        self.client.post('/api/auth/logout')
        login = self.client.post('/api/auth/login', json={'username': 'god', 'password': 'pw'})
        self.assertEqual(login.status_code, 200)

        r = self.client.get('/api/admin/users')
        self.assertEqual(r.status_code, 200)

        r = self.client.get('/api/admin/audit-logs')
        self.assertEqual(r.status_code, 200)

    def test_test_tournament_create(self):
        self._login(self.admin)
        r = self.client.post('/api/admin/test-tournament', json={'manual_username': 'manual_tester'})
        self.assertEqual(r.status_code, 201)
        test = r.get_json()['test']

        self.assertIn('bracket_url', test)
        self.assertEqual(test['manual_username'], 'manual_tester')
        self.assertTrue(test['manual_created'])
        self.assertIsNotNone(test['manual_password'])
        self.assertIsNotNone(test['next_match_id'])

        # 3 bot accounts + manual player exist; manual player is in a scheduled match
        from database import get_user_by_username, TournamentMatch
        with self.app_context:
            manual = get_user_by_username('manual_tester')
            self.assertIsNotNone(manual)
            for name in ('tournament_bot_1', 'tournament_bot_2', 'tournament_bot_3'):
                self.assertIsNotNone(get_user_by_username(name))
            match = TournamentMatch.query.get(test['next_match_id'])
            self.assertIn(manual.id, {match.player1_id, match.player2_id})
            self.assertEqual(match.status, 'scheduled')

        # Audit entry recorded for the admin action
        log = AdminAuditLog.query.filter_by(action='test_tournament.create').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.admin_user_id, self.admin.id)

    def test_test_tournament_requires_admin(self):
        self._login(self.regular)
        r = self.client.post('/api/admin/test-tournament', json={'manual_username': 'manual_tester'})
        self.assertEqual(r.status_code, 403)

    def test_test_tournament_status(self):
        self._login(self.admin)
        r = self.client.get('/api/admin/test-tournament/status')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('bots_enabled', data)
        self.assertIsInstance(data['bots_enabled'], bool)


if __name__ == '__main__':
    unittest.main()
