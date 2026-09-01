import json
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['ENV'] = 'development'

from app import app
from controllers.tournament_controller import _build_bracket
from database import (
    DiscoveryMatchAudit,
    DiscoveryProfile,
    Player,
    TournamentBracket,
    User,
    UserBlock,
    add_tournament_participant,
    create_tournament_record,
    db,
)
from hybrid.matching import ALGORITHM_VERSION, MatchResult, PairResult
from hybrid.shadow import build_participant_snapshots, record_shadow_audit


class TestHybridMatchingShadow(unittest.TestCase):
    def setUp(self):
        self.flags = (
            'HYBRID_ENABLED', 'HYBRID_PROFILE_ENABLED',
            'HYBRID_MATCHING_ENABLED', 'HYBRID_MATCHING_SHADOW_ENABLED',
        )
        self.original_flags = {key: app.config.get(key) for key in self.flags}
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
            HYBRID_MATCHING_ENABLED=False,
            HYBRID_MATCHING_SHADOW_ENABLED=True,
            HYBRID_MATCHING_TIMEOUT_MS=250,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.users = []
        for index in range(1, 5):
            user = User(
                username=f'shadow-{index}',
                email=f'shadow-{index}@test.com',
            )
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(Player(user_id=user.id))
            db.session.add(DiscoveryProfile(
                user_id=user.id,
                is_enabled=True,
                is_visible=True,
                moderation_status='approved',
                intent='selling' if index % 2 else 'seeking',
                category='services',
                subcategory='repairs',
                location='Mbabane',
                predefined_caption=(
                    'offering_services' if index % 2 else 'seeking_services'
                ),
            ))
            self.users.append(user)
        self.admin = User(
            username='shadow-admin', email='shadow-admin@test.com', is_admin=True
        )
        self.admin.set_password('pw')
        db.session.add(self.admin)
        db.session.flush()
        db.session.add(Player(user_id=self.admin.id))
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original_flags)

    def create_tournament(self, tournament_type='standard'):
        tournament = create_tournament_record(
            creator_id=self.users[0].id,
            tournament_type=tournament_type,
            tournament_name='Shadow Observation',
            max_players=64 if tournament_type == 'cup' else 4,
        )
        for user in self.users:
            add_tournament_participant(
                tournament.id,
                user.id,
                payment_status='completed',
                paid_amount=10.0,
                payment_method='promotional_credit',
            )
        tournament.current_player_count = 4
        db.session.commit()
        return tournament

    def login_admin(self):
        return self.client.post('/api/auth/login', json={
            'username': self.admin.username,
            'password': 'pw',
        })

    def test_shadow_records_proposal_without_changing_legacy_bracket(self):
        tournament = self.create_tournament()
        user_ids = [user.id for user in self.users]
        proposed = tuple(reversed(user_ids))
        fake_result = MatchResult(
            ALGORITHM_VERSION,
            'matched',
            4,
            proposed,
            (
                PairResult(proposed[0], proposed[1], 50, True, 'commercial_match', ('complementary_intent',)),
                PairResult(proposed[2], proposed[3], 50, True, 'commercial_match', ('complementary_intent',)),
            ),
            (),
            100,
            2,
            False,
        )
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None), \
             patch('hybrid.shadow.match_first_round', return_value=fake_result):
            _build_bracket(tournament)

        round_one = TournamentBracket.query.filter_by(
            tournament_id=tournament.id, round_number=1
        ).order_by(TournamentBracket.match_number).all()
        live_seed = tuple(
            user_id
            for bracket in round_one
            for user_id in (bracket.player1_id, bracket.player2_id)
        )
        self.assertEqual(live_seed, tuple(user_ids))
        audit = DiscoveryMatchAudit.query.one()
        self.assertEqual(audit.status, 'matched')
        self.assertEqual(audit.participant_count, 4)

        self.login_admin()
        response = self.client.get('/api/admin/hybrid/match-audits')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['audits'][0]
        self.assertEqual(payload['legacy_seed_order'], user_ids)
        self.assertEqual(payload['proposed_seed_order'], list(proposed))
        self.assertIsNotNone(payload['matching_duration_ms'])
        self.assertGreaterEqual(payload['matching_duration_ms'], 0)
        self.assertFalse(payload['pairing_changed'])
        self.assertEqual(
            payload['proposed_pairs'][0]['player1_username'],
            self.users[3].username,
        )
        self.assertEqual(
            payload['proposed_pairs'][0]['pair_label_display'],
            'Commercial match',
        )
        self.assertEqual(
            payload['proposed_pairs'][0]['reason_labels'],
            ['Seller and seeker complement each other'],
        )
        self.assertNotIn('Mbabane', str(payload))
        self.assertNotIn('caption', str(payload).lower())

    def test_live_flag_applies_valid_round_one_proposal_and_audits_it(self):
        tournament = self.create_tournament()
        user_ids = [user.id for user in self.users]
        proposed = (user_ids[0], user_ids[2], user_ids[1], user_ids[3])
        result = MatchResult(
            ALGORITHM_VERSION, 'matched', 4, proposed,
            (
                PairResult(proposed[0], proposed[1], 50, True, 'commercial_match', ('complementary_intent',)),
                PairResult(proposed[2], proposed[3], 50, True, 'commercial_match', ('complementary_intent',)),
            ),
            (), 100, 2, False,
        )
        app.config.update(
            HYBRID_MATCHING_ENABLED=True,
            HYBRID_MATCHING_SHADOW_ENABLED=False,
        )
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None), \
             patch('hybrid.shadow.evaluate_matching', return_value=(result, 1.25)):
            _build_bracket(tournament)

        rows = TournamentBracket.query.filter_by(
            tournament_id=tournament.id, round_number=1
        ).order_by(TournamentBracket.match_number).all()
        live_seed = tuple(
            user_id for row in rows for user_id in (row.player1_id, row.player2_id)
        )
        self.assertEqual(live_seed, proposed)
        audit = DiscoveryMatchAudit.query.one()
        self.assertEqual(audit.mode, 'live')
        self.assertEqual(json.loads(audit.legacy_seed_order_json), user_ids)
        self.assertEqual(audit.matching_duration_ms, 1.25)

        self.login_admin()
        response = self.client.get('/api/admin/hybrid/match-audits')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['mode'], 'live')

    def test_live_fallback_signal_keeps_legacy_round_one(self):
        tournament = self.create_tournament()
        user_ids = [user.id for user in self.users]
        fallback = MatchResult(
            ALGORITHM_VERSION, 'timeout', 4, (), (), (), 0, 0, True,
        )
        app.config.update(
            HYBRID_MATCHING_ENABLED=True,
            HYBRID_MATCHING_SHADOW_ENABLED=False,
        )
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None), \
             patch('hybrid.shadow.evaluate_matching', return_value=(fallback, 250.0)):
            _build_bracket(tournament)
        rows = TournamentBracket.query.filter_by(
            tournament_id=tournament.id, round_number=1
        ).order_by(TournamentBracket.match_number).all()
        self.assertEqual(
            tuple(user_id for row in rows for user_id in (row.player1_id, row.player2_id)),
            tuple(user_ids),
        )
        self.assertTrue(DiscoveryMatchAudit.query.one().legacy_fallback_recommended)

    def test_four_player_observation_pairs_complementary_profiles_only_in_audit(self):
        """Real matcher pilot: legacy stays live while two useful pairs are proposed."""
        seller_product, seeker_product, seller_service, seeker_service = self.users
        profiles = {
            seller_product.id: ('selling', 'products', 'furniture', 'Mbabane', 'selling_products'),
            seeker_product.id: ('seeking', 'products', 'furniture', 'Mbabane', 'looking_to_buy'),
            seller_service.id: ('selling', 'services', 'plumbing', 'Manzini', 'offering_services'),
            seeker_service.id: ('seeking', 'services', 'plumbing', 'Manzini', 'seeking_services'),
        }
        for user_id, values in profiles.items():
            profile = DiscoveryProfile.query.filter_by(user_id=user_id).one()
            (
                profile.intent,
                profile.category,
                profile.subcategory,
                profile.location,
                profile.predefined_caption,
            ) = values

        tournament = create_tournament_record(
            creator_id=seller_product.id,
            tournament_type='standard',
            tournament_name='Four Player Hybrid Observation',
            max_players=4,
        )
        # Deliberately register an unhelpful legacy order so the observation is clear:
        # seller-v-seller and seeker-v-seeker remain the real Round 1 bracket.
        registration_order = (
            seller_product, seller_service, seeker_service, seeker_product,
        )
        registered_at = datetime(2026, 1, 1, 12, 0, 0)
        for index, user in enumerate(registration_order):
            participant = add_tournament_participant(
                tournament.id,
                user.id,
                payment_status='completed',
                paid_amount=10.0,
                payment_method='promotional_credit',
            )
            participant.registered_at = registered_at + timedelta(seconds=index)
        tournament.current_player_count = 4
        db.session.commit()

        with patch('controllers.tournament_controller.random.shuffle', lambda values: None):
            _build_bracket(tournament)

        round_one = TournamentBracket.query.filter_by(
            tournament_id=tournament.id, round_number=1
        ).order_by(TournamentBracket.match_number).all()
        live_pairs = [
            (row.player1_id, row.player2_id)
            for row in round_one
        ]
        self.assertEqual(live_pairs, [
            (seller_product.id, seller_service.id),
            (seeker_service.id, seeker_product.id),
        ])

        audit = DiscoveryMatchAudit.query.one()
        proposed_pairs = {
            frozenset((pair['player1_id'], pair['player2_id']))
            for pair in json.loads(audit.pairs_json)
        }
        self.assertEqual(proposed_pairs, {
            frozenset((seller_product.id, seeker_product.id)),
            frozenset((seller_service.id, seeker_service.id)),
        })
        self.assertEqual(audit.hybrid_pair_count, 2)
        self.assertNotEqual(
            json.loads(audit.proposed_seed_order_json),
            json.loads(audit.legacy_seed_order_json),
        )
        for pair in json.loads(audit.pairs_json):
            self.assertEqual(pair['pair_label'], 'commercial_match')
            self.assertIn('complementary_intent', pair['reason_codes'])
            self.assertIn('category_match', pair['reason_codes'])
            self.assertIn('subcategory_match', pair['reason_codes'])
            self.assertIn('location_match', pair['reason_codes'])

        self.login_admin()
        payload = self.client.get(
            '/api/admin/hybrid/match-audits'
        ).get_json()['audits'][0]
        self.assertTrue(payload['pairing_changed'])
        self.assertEqual(
            {pair['comparison_status'] for pair in payload['proposed_pairs']},
            {'changed_from_live'},
        )
        self.assertEqual(
            {pair['pair_label_display'] for pair in payload['proposed_pairs']},
            {'Commercial match'},
        )

    def test_blocked_only_commercial_pair_falls_back_without_pairing_them(self):
        seller, seeker, fallback_one, fallback_two = self.users
        for user in (fallback_one, fallback_two):
            profile = DiscoveryProfile.query.filter_by(user_id=user.id).one()
            profile.is_enabled = False
            profile.is_visible = False
        db.session.add(UserBlock(blocker_id=seller.id, blocked_id=seeker.id))
        db.session.commit()

        tournament = self.create_tournament()
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None):
            _build_bracket(tournament)

        audit = DiscoveryMatchAudit.query.one()
        proposed_pairs = json.loads(audit.pairs_json)
        self.assertEqual(audit.status, 'no_positive_matches')
        self.assertEqual(audit.hybrid_pair_count, 0)
        self.assertTrue(audit.legacy_fallback_recommended)
        self.assertNotIn(
            frozenset((seller.id, seeker.id)),
            {
                frozenset((pair['player1_id'], pair['player2_id']))
                for pair in proposed_pairs
            },
        )
        self.assertTrue(all(not pair['hybrid_match'] for pair in proposed_pairs))

    def test_shadow_is_default_safe_and_does_not_run_when_disabled(self):
        tournament = self.create_tournament()
        app.config['HYBRID_MATCHING_SHADOW_ENABLED'] = False
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None):
            brackets = _build_bracket(tournament)
        self.assertTrue(brackets)
        self.assertEqual(DiscoveryMatchAudit.query.count(), 0)
        self.login_admin()
        self.assertEqual(
            self.client.get('/api/admin/hybrid/match-audits').status_code,
            404,
        )

    def test_admin_shadow_table_has_readable_review_columns(self):
        self.login_admin()
        response = self.client.get('/api/admin/admin')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Live Round 1', response.data)
        self.assertIn(b'Proposed Hybrid Round 1', response.data)
        self.assertIn(b'Matcher time', response.data)

    def test_shadow_failure_cannot_roll_back_or_change_live_bracket(self):
        tournament = self.create_tournament()
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None), \
             patch('hybrid.shadow.match_first_round', side_effect=RuntimeError('shadow failed')):
            brackets = _build_bracket(tournament)
        self.assertTrue(brackets)
        self.assertEqual(TournamentBracket.query.filter_by(
            tournament_id=tournament.id, round_number=1
        ).count(), 2)
        self.assertEqual(DiscoveryMatchAudit.query.count(), 0)

    def test_cup_is_never_observed_by_ordinary_shadow_adapter(self):
        tournament = self.create_tournament(tournament_type='cup')
        with patch('controllers.tournament_controller.random.shuffle', lambda values: None):
            _build_bracket(tournament)
        self.assertEqual(DiscoveryMatchAudit.query.count(), 0)

    def test_snapshot_adapter_applies_mutual_blocks_and_moderation(self):
        first, second = self.users[:2]
        db.session.add(UserBlock(blocker_id=first.id, blocked_id=second.id))
        second_profile = DiscoveryProfile.query.filter_by(user_id=second.id).one()
        second_profile.moderation_status = 'rejected'
        second_profile.is_visible = False
        db.session.commit()
        snapshots = {
            snapshot.user_id: snapshot
            for snapshot in build_participant_snapshots(
                [user.id for user in self.users]
            )
        }
        self.assertIn(second.id, snapshots[first.id].blocked_user_ids)
        self.assertIn(first.id, snapshots[second.id].blocked_user_ids)
        self.assertFalse(snapshots[second.id].discovery_authorized)

    def test_shadow_audit_is_idempotent_per_tournament_and_algorithm(self):
        tournament = self.create_tournament()
        user_ids = [user.id for user in self.users]
        first = record_shadow_audit(tournament, user_ids, user_ids, app.config)
        second = record_shadow_audit(tournament, user_ids, list(reversed(user_ids)), app.config)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(DiscoveryMatchAudit.query.count(), 1)


if __name__ == '__main__':
    unittest.main()
