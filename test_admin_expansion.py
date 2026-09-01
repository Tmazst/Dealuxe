import os
import time
import unittest
from datetime import datetime

os.environ['ENV'] = 'development'

from app import app
from database import (
    db,
    User,
    Player,
    Tournament,
    TournamentParticipant,
    Transaction,
    TX_WALLET_TOPUP,
    AdminAuditLog,
    Dispute,
    WalletAdjustment,
    CupQualification,
    TournamentBracket,
    TournamentMatch,
    TournamentPrizePool,
    create_tournament_record,
    add_tournament_participant,
    get_player_by_user_id,
)


class TestAdminExpansion(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['MOJAPOS_MOCK_MODE'] = 'true'
        app.config['CUP_ENABLED'] = False
        app.config['CUP_CASH_PAYOUTS_ENABLED'] = False
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
        r = self.client.get('/api/admin/cup-tournaments/1/placements')
        self.assertEqual(r.status_code, 403)
        r = self.client.get('/api/admin/cup-replacement-candidates')
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

    def test_admin_replaces_absent_qualifier_with_recorded_runner_up(self):
        active_id, _, _ = self._seed_cup_roster()
        runner_up = User(
            username='runner_replacement',
            email='runner_replacement@test.com',
            password_hash='not-used',
        )
        referral_leader = User(
            username='invite_leader',
            email='invite_leader@test.com',
            password_hash='not-used',
            verified_referral_count=7,
        )
        db.session.add_all([runner_up, referral_leader])
        db.session.flush()
        source = create_tournament_record(
            creator_id=self.admin.id,
            tournament_type='premium',
            tournament_name='Eight Player Runner-up Source',
            entry_fee=10.0,
            max_players=8,
        )
        source.status = 'completed'
        source.runner_up_id = runner_up.id
        db.session.commit()
        self._login(self.admin)

        candidates = self.client.get('/api/admin/cup-replacement-candidates')
        self.assertEqual(candidates.status_code, 200)
        payload = candidates.get_json()
        self.assertIn(runner_up.id, {
            item['user_id'] for item in payload['runner_ups']
        })
        self.assertIn(referral_leader.id, {
            item['user_id'] for item in payload['referral_leaders']
        })

        replacement = self.client.post(
            f'/api/admin/cup-qualifications/{active_id}/replace-absent',
            json={
                'candidate_user_id': runner_up.id,
                'source_type': 'runner_up',
                'source_tournament_id': source.id,
                'reason': 'Qualifier did not arrive for Cup check-in',
            },
        )
        self.assertEqual(replacement.status_code, 200, replacement.get_json())
        qualification = CupQualification.query.get(active_id)
        self.assertEqual(qualification.user_id, runner_up.id)
        self.assertEqual(qualification.original_user_id, self.regular.id)
        self.assertEqual(qualification.replacement_source_type, 'runner_up')
        self.assertEqual(
            qualification.replacement_source_reference, f'tournament:{source.id}'
        )
        self.assertIsNotNone(AdminAuditLog.query.filter_by(
            action='cup_roster.replace_absent', entity_id=active_id
        ).first())

    def test_live_cup_replacement_updates_unstarted_round_one_match(self):
        app.config['CUP_ENABLED'] = True
        self._add_cup_qualifiers(64)
        self._login(self.admin)
        created = self.client.post('/api/admin/cup-tournaments', json={})
        self.assertEqual(created.status_code, 201, created.get_json())
        cup_id = created.get_json()['cup']['tournament_id']
        qualification = CupQualification.query.filter_by(
            event_key=app.config['CUP_EVENT_KEY']
        ).order_by(CupQualification.id.asc()).first()
        absent_user_id = qualification.user_id
        participant = TournamentParticipant.query.filter_by(
            tournament_id=cup_id, user_id=absent_user_id
        ).first()
        bracket = TournamentBracket.query.filter(
            TournamentBracket.tournament_id == cup_id,
            TournamentBracket.round_number == 1,
            (TournamentBracket.player1_id == absent_user_id)
            | (TournamentBracket.player2_id == absent_user_id),
        ).first()
        match = TournamentMatch.query.filter_by(bracket_id=bracket.id).first()

        referral_pick = User(
            username='live_referral_pick',
            email='live_referral_pick@test.com',
            password_hash='not-used',
            verified_referral_count=12,
        )
        db.session.add(referral_pick)
        db.session.commit()
        replaced = self.client.post(
            f'/api/admin/cup-qualifications/{qualification.id}/replace-absent',
            json={
                'candidate_user_id': referral_pick.id,
                'source_type': 'referral_leader',
                'reason': 'Confirmed absent before Round 1 started',
            },
        )
        self.assertEqual(replaced.status_code, 200, replaced.get_json())
        db.session.refresh(participant)
        db.session.refresh(bracket)
        db.session.refresh(match)
        self.assertEqual(participant.user_id, referral_pick.id)
        self.assertIn(referral_pick.id, {bracket.player1_id, bracket.player2_id})
        self.assertIn(referral_pick.id, {match.player1_id, match.player2_id})
        self.assertNotIn(absent_user_id, {match.player1_id, match.player2_id})

        second_pick = User(
            username='late_replacement',
            email='late_replacement@test.com',
            password_hash='not-used',
            verified_referral_count=5,
        )
        db.session.add(second_pick)
        match.started_at = datetime.utcnow()
        match.status = 'in_progress'
        db.session.commit()
        too_late = self.client.post(
            f'/api/admin/cup-qualifications/{qualification.id}/replace-absent',
            json={
                'candidate_user_id': second_pick.id,
                'source_type': 'referral_leader',
                'reason': 'Attempted after match start',
            },
        )
        self.assertEqual(too_late.status_code, 400)
        self.assertIn('once the player', too_late.get_json()['error'])

    def _add_cup_qualifiers(self, count):
        event_key = app.config['CUP_EVENT_KEY']
        for index in range(count):
            user = User(
                username=f'cup_player_{index:02d}',
                email=f'cup_player_{index:02d}@test.com',
                password_hash='not-used',
            )
            db.session.add(user)
            db.session.flush()
            source = create_tournament_record(
                creator_id=self.admin.id,
                tournament_type='standard',
                tournament_name=f'Cup Qualifier {index + 1}',
                entry_fee=10.0,
                max_players=4,
            )
            db.session.add(CupQualification(
                source_tournament_id=source.id,
                user_id=user.id,
                season=app.config['CUP_SEASON'],
                event_key=event_key,
                status='checked_in' if index % 2 else 'qualified',
                seat_key=f'{event_key}:{user.id}',
            ))
        db.session.commit()

    def test_admin_creates_payout_free_64_player_cup_from_active_roster(self):
        app.config['CUP_ENABLED'] = True
        self._add_cup_qualifiers(64)
        self._login(self.admin)

        started_at = time.perf_counter()
        response = self.client.post('/api/admin/cup-tournaments', json={
            'tournament_name': '2026 Pilot Cup',
        })
        elapsed = time.perf_counter() - started_at
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertLess(elapsed, 5.0)
        payload = response.get_json()['cup']
        self.assertEqual(payload['players'], 64)
        self.assertEqual(payload['bracket_slots'], 64)
        self.assertFalse(payload['cash_prizes_enabled'])

        cup = Tournament.query.get(payload['tournament_id'])
        self.assertEqual(cup.tournament_type, 'cup')
        self.assertEqual(cup.max_players, 64)
        self.assertEqual(cup.current_player_count, 64)
        self.assertEqual(cup.status, 'in_progress')
        self.assertEqual(cup.entry_fee, 0.0)
        self.assertEqual(cup.prize_pool_amount, 0.0)
        participants = TournamentParticipant.query.filter_by(
            tournament_id=cup.id
        ).all()
        self.assertEqual(len(participants), 64)
        self.assertEqual(
            {participant.payment_method for participant in participants},
            {'cup_qualification'},
        )

        brackets = TournamentBracket.query.filter_by(tournament_id=cup.id).all()
        self.assertEqual(len(brackets), 64)
        round_one = [row for row in brackets if row.round_number == 1]
        self.assertEqual(len(round_one), 32)
        self.assertEqual({row.round_name for row in round_one}, {'Round of 64'})
        self.assertEqual(
            TournamentMatch.query.filter_by(tournament_id=cup.id).count(), 32
        )
        self.assertTrue(all(
            row.prize_amount == 0.0
            for row in TournamentPrizePool.query.filter_by(tournament_id=cup.id).all()
        ))
        self.assertIsNotNone(AdminAuditLog.query.filter_by(
            action='cup_tournament.create', entity_id=cup.id
        ).first())

        duplicate = self.client.post('/api/admin/cup-tournaments', json={})
        self.assertEqual(duplicate.status_code, 400)

    def test_cup_creation_requires_feature_flag_and_exact_roster(self):
        self._add_cup_qualifiers(63)
        self._login(self.admin)

        disabled = self.client.post('/api/admin/cup-tournaments', json={})
        self.assertEqual(disabled.status_code, 400)
        self.assertIn('CUP_ENABLED', disabled.get_json()['error'])

        app.config['CUP_ENABLED'] = True
        incomplete = self.client.post('/api/admin/cup-tournaments', json={})
        self.assertEqual(incomplete.status_code, 400)
        self.assertIn('exactly 64', incomplete.get_json()['error'])
        self.assertEqual(Tournament.query.filter_by(tournament_type='cup').count(), 0)

    def _seed_cup_placement_state(self):
        app.config['CUP_ENABLED'] = True
        self._add_cup_qualifiers(64)
        self._login(self.admin)
        created = self.client.post('/api/admin/cup-tournaments', json={})
        self.assertEqual(created.status_code, 201, created.get_json())
        cup_id = created.get_json()['cup']['tournament_id']
        participants = TournamentParticipant.query.filter_by(
            tournament_id=cup_id
        ).order_by(TournamentParticipant.user_id.asc()).all()
        quarter_finalists = participants[:8]
        manual_candidates = participants[8:10]
        for participant in manual_candidates:
            participant.status = 'eliminated'

        quarter_final_brackets = TournamentBracket.query.filter_by(
            tournament_id=cup_id, round_name='Quarter-Final'
        ).order_by(TournamentBracket.match_number.asc()).all()
        losers = []
        for index, bracket in enumerate(quarter_final_brackets):
            winner = quarter_finalists[index * 2]
            loser = quarter_finalists[index * 2 + 1]
            bracket.player1_id = winner.user_id
            bracket.player2_id = loser.user_id
            bracket.winner_id = winner.user_id
            bracket.status = 'completed'
            winner.status = 'active'
            loser.status = 'eliminated'
            match = TournamentMatch(
                tournament_id=cup_id,
                bracket_id=bracket.id,
                player1_id=winner.user_id,
                player2_id=loser.user_id,
                winner_id=winner.user_id,
                loser_id=loser.user_id,
                status='completed',
                card_count=6,
                bet_amount=0.0,
            )
            db.session.add(match)
            db.session.flush()
            bracket.match_id = match.id
            losers.append(loser.user_id)
        db.session.commit()
        return cup_id, losers, [item.user_id for item in manual_candidates], quarter_finalists

    def test_admin_orders_cup_positions_5_to_10_with_audit(self):
        cup_id, losers, manual_candidates, quarter_finalists = (
            self._seed_cup_placement_state()
        )

        placement_state = self.client.get(
            f'/api/admin/cup-tournaments/{cup_id}/placements'
        )
        self.assertEqual(placement_state.status_code, 200)
        self.assertTrue(placement_state.get_json()['quarter_finals_complete'])
        self.assertEqual(
            {item['user_id'] for item in placement_state.get_json()['eligible_5_8']},
            set(losers),
        )

        invalid = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/5-8',
            json={
                'ordered_user_ids': losers[:3] + [quarter_finalists[0].user_id],
                'reason': 'Invalid attempt',
            },
        )
        self.assertEqual(invalid.status_code, 400)

        missing_reason = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/5-8',
            json={'ordered_user_ids': losers},
        )
        self.assertEqual(missing_reason.status_code, 400)

        ordered_losers = list(reversed(losers))
        positions_5_8 = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/5-8',
            json={
                'ordered_user_ids': ordered_losers,
                'reason': 'Approved Cup tie-break ordering',
            },
        )
        self.assertEqual(positions_5_8.status_code, 200, positions_5_8.get_json())

        invalid_manual = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/9-10',
            json={
                'ordered_user_ids': [manual_candidates[0], quarter_finalists[0].user_id],
                'reason': 'Invalid quarter-finalist selection',
            },
        )
        self.assertEqual(invalid_manual.status_code, 400)

        positions_9_10 = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/9-10',
            json={
                'ordered_user_ids': manual_candidates,
                'reason': 'Administrator wild-card placement decision',
            },
        )
        self.assertEqual(positions_9_10.status_code, 200, positions_9_10.get_json())
        assignments = positions_9_10.get_json()['assignments']
        for placement, user_id in enumerate(ordered_losers, start=5):
            self.assertEqual(assignments[str(placement)]['user_id'], user_id)
        self.assertEqual(assignments['9']['user_id'], manual_candidates[0])
        self.assertEqual(assignments['10']['user_id'], manual_candidates[1])

        actions = {
            log.action for log in AdminAuditLog.query.filter_by(
                entity_type='tournament', entity_id=cup_id
            ).all()
        }
        self.assertIn('cup_placement.order_5_8', actions)
        self.assertIn('cup_placement.select_9_10', actions)

    def test_cup_finalization_assigns_fourth_place_without_cash(self):
        cup_id, _, _, quarter_finalists = self._seed_cup_placement_state()
        cup = Tournament.query.get(cup_id)
        cup.winner_id = quarter_finalists[0].user_id
        cup.runner_up_id = quarter_finalists[2].user_id
        cup.third_place_id = quarter_finalists[4].user_id
        fourth_id = quarter_finalists[6].user_id
        third_bracket = TournamentBracket.query.filter_by(
            tournament_id=cup_id, round_name='Third-Place'
        ).first()
        third_match = TournamentMatch(
            tournament_id=cup_id,
            bracket_id=third_bracket.id,
            player1_id=cup.third_place_id,
            player2_id=fourth_id,
            winner_id=cup.third_place_id,
            loser_id=fourth_id,
            status='completed',
            card_count=6,
            bet_amount=0.0,
        )
        db.session.add(third_match)
        db.session.flush()
        third_bracket.match_id = third_match.id
        third_bracket.status = 'completed'

        from controllers.tournament_controller import _finalize_tournament
        _finalize_tournament(cup)
        db.session.commit()

        placements = {
            participant.final_placement: participant.user_id
            for participant in TournamentParticipant.query.filter_by(
                tournament_id=cup_id
            ).all()
            if participant.final_placement is not None
        }
        self.assertEqual(placements[1], cup.winner_id)
        self.assertEqual(placements[2], cup.runner_up_id)
        self.assertEqual(placements[3], cup.third_place_id)
        self.assertEqual(placements[4], fourth_id)
        self.assertTrue(all(
            participant.prize_awarded == 0.0
            for participant in TournamentParticipant.query.filter_by(
                tournament_id=cup_id
            ).all()
        ))

    def test_64_player_cup_supports_one_complete_distinct_top_ten_result(self):
        cup_id, quarter_final_losers, manual_candidates, quarter_finalists = (
            self._seed_cup_placement_state()
        )

        ordered_losers = list(reversed(quarter_final_losers))
        positions_5_8 = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/5-8',
            json={
                'ordered_user_ids': ordered_losers,
                'reason': 'Approved final Cup ordering for positions 5-8',
            },
        )
        self.assertEqual(positions_5_8.status_code, 200, positions_5_8.get_json())
        positions_9_10 = self.client.patch(
            f'/api/admin/cup-tournaments/{cup_id}/placements/9-10',
            json={
                'ordered_user_ids': manual_candidates,
                'reason': 'Approved final Cup selections for positions 9-10',
            },
        )
        self.assertEqual(positions_9_10.status_code, 200, positions_9_10.get_json())

        cup = db.session.get(Tournament, cup_id)
        cup.winner_id = quarter_finalists[0].user_id
        cup.runner_up_id = quarter_finalists[2].user_id
        cup.third_place_id = quarter_finalists[4].user_id
        fourth_id = quarter_finalists[6].user_id
        third_bracket = TournamentBracket.query.filter_by(
            tournament_id=cup_id, round_name='Third-Place'
        ).one()
        third_match = TournamentMatch(
            tournament_id=cup_id,
            bracket_id=third_bracket.id,
            player1_id=cup.third_place_id,
            player2_id=fourth_id,
            winner_id=cup.third_place_id,
            loser_id=fourth_id,
            status='completed',
            card_count=6,
            bet_amount=0.0,
        )
        db.session.add(third_match)
        db.session.flush()
        third_bracket.match_id = third_match.id
        third_bracket.status = 'completed'

        from controllers.tournament_controller import _finalize_tournament
        _finalize_tournament(cup)
        db.session.commit()

        placed = {
            participant.final_placement: participant.user_id
            for participant in TournamentParticipant.query.filter_by(
                tournament_id=cup_id
            ).all()
            if participant.final_placement is not None
        }
        self.assertEqual(set(placed), set(range(1, 11)))
        self.assertEqual(len(set(placed.values())), 10)
        self.assertEqual(placed[1], cup.winner_id)
        self.assertEqual(placed[2], cup.runner_up_id)
        self.assertEqual(placed[3], cup.third_place_id)
        self.assertEqual(placed[4], fourth_id)
        self.assertEqual(
            [placed[position] for position in range(5, 9)], ordered_losers
        )
        self.assertEqual(
            [placed[position] for position in (9, 10)], manual_candidates
        )
        self.assertEqual(
            TournamentParticipant.query.filter_by(tournament_id=cup_id).count(),
            64,
        )

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

    def test_admin_maintains_verified_invite_count(self):
        self._login(self.admin)
        updated = self.client.patch(
            f'/api/admin/users/{self.regular.id}',
            json={'verified_referral_count': 9},
        )
        self.assertEqual(updated.status_code, 200, updated.get_json())
        self.assertEqual(updated.get_json()['user']['verified_referral_count'], 9)
        self.assertEqual(User.query.get(self.regular.id).verified_referral_count, 9)

        rejected = self.client.patch(
            f'/api/admin/users/{self.regular.id}',
            json={'verified_referral_count': -1},
        )
        self.assertEqual(rejected.status_code, 400)

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
