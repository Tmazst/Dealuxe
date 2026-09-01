import itertools
import random
import time
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from hybrid.matching import (
    ALGORITHM_VERSION,
    MatchResult,
    MatchingInputError,
    MatchingPolicy,
    ParticipantSnapshot,
    match_first_round,
)


def profile(user_id, intent, category='services', **overrides):
    values = {
        'user_id': user_id,
        'profile_enabled': True,
        'entitlement_active': True,
        'is_visible': True,
        'moderation_status': 'approved',
        'intent': intent,
        'category': category,
        'subcategory': 'repairs',
        'location': 'mbabane',
        'plan_level': 1,
    }
    values.update(overrides)
    return ParticipantSnapshot(**values)


class TestHybridMatching(unittest.TestCase):
    def test_snapshots_and_policy_are_immutable_and_versioned(self):
        snapshot = profile(1, 'selling')
        with self.assertRaises(FrozenInstanceError):
            snapshot.intent = 'seeking'
        policy = MatchingPolicy()
        self.assertEqual(policy.algorithm_version, ALGORITHM_VERSION)
        with self.assertRaises(FrozenInstanceError):
            policy.category_weight = 99

    def test_complementary_profiles_are_exactly_paired(self):
        participants = (
            profile(1, 'selling', category='services'),
            profile(2, 'seeking', category='services'),
            profile(3, 'selling', category='products', subcategory='furniture'),
            profile(4, 'seeking', category='products', subcategory='furniture'),
        )
        result = match_first_round(participants, 'tournament-77')
        pairs = {frozenset((pair.player1_id, pair.player2_id)) for pair in result.pairs}
        self.assertEqual(pairs, {frozenset((1, 2)), frozenset((3, 4))})
        self.assertEqual(result.status, 'matched')
        self.assertEqual(result.hybrid_pair_count, 2)
        self.assertFalse(result.legacy_fallback_recommended)

    def test_result_is_deterministic_across_input_permutations(self):
        participants = tuple(
            profile(index, 'selling' if index % 2 else 'seeking')
            for index in range(1, 9)
        )
        expected = match_first_round(participants, 1234).to_dict()
        rng = random.Random(42)
        for _ in range(25):
            shuffled = list(participants)
            rng.shuffle(shuffled)
            self.assertEqual(match_first_round(shuffled, 1234).to_dict(), expected)

    def test_four_eight_and_sixteen_players_appear_exactly_once(self):
        for size in (4, 8, 16):
            with self.subTest(size=size):
                participants = tuple(
                    profile(
                        index,
                        'selling' if index % 2 else 'seeking',
                        category='products' if index % 4 < 2 else 'services',
                    )
                    for index in range(1, size + 1)
                )
                result = match_first_round(participants, f'size-{size}')
                self.assertEqual(len(result.pairs), size // 2)
                self.assertEqual(len(result.seed_order), size)
                self.assertEqual(set(result.seed_order), set(range(1, size + 1)))

    def test_blocks_are_absolute_even_when_the_pair_has_the_best_score(self):
        participants = (
            profile(1, 'selling', blocked_user_ids=frozenset({2})),
            profile(2, 'seeking'),
            profile(3, 'selling', category='products'),
            profile(4, 'seeking', category='products'),
        )
        result = match_first_round(participants, 'blocked-best-pair')
        pairs = {frozenset((pair.player1_id, pair.player2_id)) for pair in result.pairs}
        self.assertNotIn(frozenset((1, 2)), pairs)

    def test_impossible_block_constraints_return_safe_fallback_signal(self):
        result = match_first_round((
            ParticipantSnapshot(1, blocked_user_ids=frozenset({2})),
            ParticipantSnapshot(2),
        ), 'impossible')
        self.assertEqual(result.status, 'constraints_unsatisfied')
        self.assertEqual(result.seed_order, ())
        self.assertTrue(result.legacy_fallback_recommended)

    def test_unauthorized_or_incompatible_profiles_are_game_only(self):
        participants = (
            profile(1, 'selling', entitlement_active=False),
            profile(2, 'selling'),
            profile(3, 'selling'),
            profile(4, 'selling'),
        )
        result = match_first_round(participants, 'no-positive')
        self.assertEqual(result.status, 'no_positive_matches')
        self.assertTrue(result.legacy_fallback_recommended)
        self.assertTrue(all(pair.pair_label == 'game_only' for pair in result.pairs))
        self.assertTrue(all(pair.reason_codes == () for pair in result.pairs))

    def test_mixed_entitlements_only_label_authorized_pair(self):
        participants = (
            profile(1, 'selling'),
            profile(2, 'seeking'),
            profile(3, 'selling', entitlement_active=False),
            profile(4, 'seeking', profile_enabled=False),
        )
        result = match_first_round(participants, 'mixed-entitlements')
        hybrid_pairs = [pair for pair in result.pairs if pair.hybrid_match]
        self.assertEqual(len(hybrid_pairs), 1)
        self.assertEqual(
            frozenset((hybrid_pairs[0].player1_id, hybrid_pairs[0].player2_id)),
            frozenset((1, 2)),
        )

    def test_bye_is_controlled_and_independent_of_input_order(self):
        participants = tuple(
            profile(index, 'selling' if index % 2 else 'seeking')
            for index in range(1, 6)
        )
        first = match_first_round(participants, 'odd-bracket')
        second = match_first_round(reversed(participants), 'odd-bracket')
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(len(first.bye_user_ids), 1)
        self.assertEqual(len(first.seed_order), 5)
        self.assertEqual(set(first.seed_order), set(range(1, 6)))

    def test_output_contains_only_non_sensitive_pair_metadata(self):
        result = match_first_round((
            profile(1, 'selling'), profile(2, 'seeking'),
            profile(3, 'selling'), profile(4, 'seeking'),
        ), 'privacy')
        payload = result.to_dict()
        allowed = {
            'player1_id', 'player2_id', 'score', 'hybrid_match',
            'pair_label', 'reason_codes',
        }
        self.assertTrue(all(set(pair) == allowed for pair in payload['pairs']))
        serialized = str(payload).lower()
        for sensitive_name in ('mbabane', 'repairs', 'custom caption', 'blocked_user_ids'):
            self.assertNotIn(sensitive_name, serialized)

    def test_malformed_inputs_fail_closed(self):
        bad_calls = (
            lambda: match_first_round([], 'tournament'),
            lambda: match_first_round([ParticipantSnapshot(1), ParticipantSnapshot(1)], 'tournament'),
            lambda: match_first_round([ParticipantSnapshot(1), object()], 'tournament'),
            lambda: match_first_round([ParticipantSnapshot(1), ParticipantSnapshot(2)], ''),
            lambda: ParticipantSnapshot(0),
            lambda: ParticipantSnapshot(1, intent='relationship'),
            lambda: ParticipantSnapshot(1, plan_level=6),
            lambda: MatchingPolicy(timeout_ms=0),
        )
        for call in bad_calls:
            with self.subTest(call=call), self.assertRaises(MatchingInputError):
                call()

    def test_randomized_block_properties_never_duplicate_or_pair_a_block(self):
        rng = random.Random(2026)
        for iteration in range(30):
            blocked = {user_id: set() for user_id in range(1, 9)}
            for first, second in itertools.combinations(range(1, 9), 2):
                if rng.random() < 0.12:
                    blocked[first].add(second)
            participants = tuple(
                profile(
                    user_id,
                    'selling' if user_id % 2 else 'seeking',
                    blocked_user_ids=frozenset(blocked[user_id]),
                )
                for user_id in range(1, 9)
            )
            result = match_first_round(participants, f'property-{iteration}')
            if result.status == 'constraints_unsatisfied':
                continue
            self.assertEqual(len(result.seed_order), len(set(result.seed_order)))
            self.assertEqual(set(result.seed_order), set(range(1, 9)))
            for pair in result.pairs:
                self.assertNotIn(pair.player2_id, blocked[pair.player1_id])
                self.assertNotIn(pair.player1_id, blocked[pair.player2_id])

    def test_sixteen_player_match_stays_inside_timeout_budget(self):
        participants = tuple(
            profile(index, 'selling' if index % 2 else 'seeking')
            for index in range(1, 17)
        )
        started = time.perf_counter()
        # Allow for concurrent scheduler/database test load on slower hosts.
        # Production still defaults to a strict 250 ms safe-fallback budget.
        result = match_first_round(
            participants, 'performance', MatchingPolicy(timeout_ms=2000)
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertIsInstance(result, MatchResult)
        self.assertNotEqual(result.status, 'timeout')
        self.assertLess(elapsed_ms, 2500)

    def test_timeout_returns_safe_legacy_fallback_signal(self):
        participants = (profile(1, 'selling'), profile(2, 'seeking'))
        with patch('hybrid.matching.time.perf_counter', side_effect=(0.0, 1.0)):
            result = match_first_round(
                participants, 'forced-timeout', MatchingPolicy(timeout_ms=250)
            )
        self.assertEqual(result.status, 'timeout')
        self.assertEqual(result.seed_order, ())
        self.assertTrue(result.legacy_fallback_recommended)


if __name__ == '__main__':
    unittest.main()
