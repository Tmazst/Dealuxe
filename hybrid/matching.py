"""Pure, deterministic Hybrid Round 1 matcher with no Flask or database access."""

from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import time


ALGORITHM_VERSION = 'hybrid-round1-v1'
SUPPORTED_TOURNAMENT_SIZES = frozenset({4, 8, 16})
VALID_INTENTS = frozenset({'selling', 'seeking', 'collaboration'})
VISIBLE_MODERATION_STATES = frozenset({'approved', 'not_required'})


class MatchingInputError(ValueError):
    """Raised when a caller supplies an invalid immutable snapshot."""


class MatchingTimeoutError(RuntimeError):
    """Internal signal used to return a safe legacy-fallback result."""


def _normalized_optional(value, field_name, maximum):
    if value is None:
        return None
    if not isinstance(value, str):
        raise MatchingInputError(f'{field_name} must be text or null')
    value = value.strip().casefold()
    if len(value) > maximum:
        raise MatchingInputError(f'{field_name} is too long')
    return value or None


@dataclass(frozen=True)
class ParticipantSnapshot:
    """Non-sensitive, immutable matching input captured at bracket lock time."""

    user_id: int
    profile_enabled: bool = False
    entitlement_active: bool = False
    suspended: bool = False
    is_visible: bool = False
    moderation_status: str = 'not_required'
    intent: str | None = None
    category: str | None = None
    subcategory: str | None = None
    location: str | None = None
    plan_level: int = 0
    blocked_user_ids: frozenset[int] = field(default_factory=frozenset)

    def __post_init__(self):
        if isinstance(self.user_id, bool) or not isinstance(self.user_id, int) or self.user_id <= 0:
            raise MatchingInputError('user_id must be a positive integer')
        for field_name in (
            'profile_enabled', 'entitlement_active', 'suspended', 'is_visible',
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise MatchingInputError(f'{field_name} must be true or false')
        if isinstance(self.plan_level, bool) or not isinstance(self.plan_level, int):
            raise MatchingInputError('plan_level must be an integer')
        if not 0 <= self.plan_level <= 5:
            raise MatchingInputError('plan_level must be between 0 and 5')

        intent = _normalized_optional(self.intent, 'intent', 30)
        if intent is not None and intent not in VALID_INTENTS:
            raise MatchingInputError('intent is invalid')
        object.__setattr__(self, 'intent', intent)
        object.__setattr__(
            self, 'category', _normalized_optional(self.category, 'category', 50)
        )
        object.__setattr__(
            self, 'subcategory',
            _normalized_optional(self.subcategory, 'subcategory', 80),
        )
        object.__setattr__(
            self, 'location', _normalized_optional(self.location, 'location', 120)
        )
        moderation_status = _normalized_optional(
            self.moderation_status, 'moderation_status', 30
        )
        object.__setattr__(self, 'moderation_status', moderation_status or 'not_required')

        try:
            blocked = frozenset(self.blocked_user_ids)
        except TypeError as exc:
            raise MatchingInputError('blocked_user_ids must be an iterable of user IDs') from exc
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in blocked
        ):
            raise MatchingInputError('blocked_user_ids must contain positive integers')
        object.__setattr__(self, 'blocked_user_ids', blocked)

    @property
    def discovery_authorized(self):
        return bool(
            self.profile_enabled
            and self.entitlement_active
            and not self.suspended
            and self.is_visible
            and self.moderation_status in VISIBLE_MODERATION_STATES
            and self.intent
        )


@dataclass(frozen=True)
class MatchingPolicy:
    algorithm_version: str = ALGORITHM_VERSION
    complementary_intent_weight: int = 50
    collaboration_pair_weight: int = 35
    collaboration_open_weight: int = 20
    category_weight: int = 25
    subcategory_weight: int = 12
    location_weight: int = 8
    plan_level_weight: int = 2
    timeout_ms: int = 250

    def __post_init__(self):
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version.strip():
            raise MatchingInputError('algorithm_version is required')
        for field_name in (
            'complementary_intent_weight', 'collaboration_pair_weight',
            'collaboration_open_weight', 'category_weight', 'subcategory_weight',
            'location_weight', 'plan_level_weight',
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MatchingInputError(f'{field_name} must be a non-negative integer')
        if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
            raise MatchingInputError('timeout_ms must be an integer')
        if not 1 <= self.timeout_ms <= 5000:
            raise MatchingInputError('timeout_ms must be between 1 and 5000')


@dataclass(frozen=True)
class PairResult:
    player1_id: int
    player2_id: int
    score: int
    hybrid_match: bool
    pair_label: str
    reason_codes: tuple[str, ...]

    def to_dict(self):
        return {
            'player1_id': self.player1_id,
            'player2_id': self.player2_id,
            'score': self.score,
            'hybrid_match': self.hybrid_match,
            'pair_label': self.pair_label,
            'reason_codes': list(self.reason_codes),
        }


@dataclass(frozen=True)
class MatchResult:
    algorithm_version: str
    status: str
    participant_count: int
    seed_order: tuple[int, ...]
    pairs: tuple[PairResult, ...]
    bye_user_ids: tuple[int, ...]
    total_score: int
    hybrid_pair_count: int
    legacy_fallback_recommended: bool

    def to_dict(self):
        return {
            'algorithm_version': self.algorithm_version,
            'status': self.status,
            'participant_count': self.participant_count,
            'seed_order': list(self.seed_order),
            'pairs': [pair.to_dict() for pair in self.pairs],
            'bye_user_ids': list(self.bye_user_ids),
            'total_score': self.total_score,
            'hybrid_pair_count': self.hybrid_pair_count,
            'legacy_fallback_recommended': self.legacy_fallback_recommended,
        }


@dataclass(frozen=True)
class _Edge:
    first_index: int
    second_index: int
    score: int
    reasons: tuple[str, ...]
    tie_value: int


@dataclass(frozen=True)
class _Plan:
    score: int
    hybrid_count: int
    edges: tuple[_Edge, ...]
    tie_signature: tuple[int, ...]


def _tie_value(tournament_key, algorithm_version, *user_ids):
    ids = ':'.join(str(value) for value in sorted(user_ids))
    material = f'{algorithm_version}:{tournament_key}:{ids}'.encode('utf-8')
    return int.from_bytes(hashlib.sha256(material).digest()[:8], 'big')


def _blocked(first, second):
    return (
        second.user_id in first.blocked_user_ids
        or first.user_id in second.blocked_user_ids
    )


def _score_edge(first, second, policy):
    if not first.discovery_authorized or not second.discovery_authorized:
        return 0, ()

    intent_pair = frozenset({first.intent, second.intent})
    reasons = []
    score = 0
    if intent_pair == frozenset({'selling', 'seeking'}):
        score += policy.complementary_intent_weight
        reasons.append('complementary_intent')
    elif first.intent == second.intent == 'collaboration':
        score += policy.collaboration_pair_weight
        reasons.append('collaboration_fit')
    elif 'collaboration' in intent_pair:
        score += policy.collaboration_open_weight
        reasons.append('collaboration_open')
    else:
        return 0, ()

    if first.category and first.category == second.category:
        score += policy.category_weight
        reasons.append('category_match')
    if first.subcategory and first.subcategory == second.subcategory:
        score += policy.subcategory_weight
        reasons.append('subcategory_match')
    if first.location and first.location == second.location:
        score += policy.location_weight
        reasons.append('location_match')
    shared_plan_level = min(first.plan_level, second.plan_level)
    if shared_plan_level:
        score += shared_plan_level * policy.plan_level_weight
        reasons.append('plan_level')
    return score, tuple(reasons)


def _better(candidate, incumbent):
    if incumbent is None:
        return True
    candidate_primary = (candidate.score, candidate.hybrid_count)
    incumbent_primary = (incumbent.score, incumbent.hybrid_count)
    if candidate_primary != incumbent_primary:
        return candidate_primary > incumbent_primary
    return candidate.tie_signature < incumbent.tie_signature


def _solve_even(participants, tournament_key, policy, deadline):
    count = len(participants)
    edges = {}
    for first_index in range(count):
        for second_index in range(first_index + 1, count):
            first = participants[first_index]
            second = participants[second_index]
            if _blocked(first, second):
                continue
            score, reasons = _score_edge(first, second, policy)
            edges[(first_index, second_index)] = _Edge(
                first_index,
                second_index,
                score,
                reasons,
                _tie_value(
                    tournament_key, policy.algorithm_version,
                    first.user_id, second.user_id,
                ),
            )

    calls = 0

    @lru_cache(maxsize=None)
    def solve(mask):
        nonlocal calls
        calls += 1
        if calls % 128 == 0 and time.perf_counter() > deadline:
            raise MatchingTimeoutError()
        if mask == 0:
            return _Plan(0, 0, (), ())
        first_index = (mask & -mask).bit_length() - 1
        remaining = mask & ~(1 << first_index)
        best = None
        candidate_bits = remaining
        while candidate_bits:
            second_index = (candidate_bits & -candidate_bits).bit_length() - 1
            candidate_bits &= ~(1 << second_index)
            edge = edges.get((first_index, second_index))
            if edge is None:
                continue
            suffix = solve(remaining & ~(1 << second_index))
            if suffix is None:
                continue
            tie_signature = tuple(sorted((edge.tie_value, *suffix.tie_signature)))
            candidate = _Plan(
                edge.score + suffix.score,
                (1 if edge.score > 0 else 0) + suffix.hybrid_count,
                (edge, *suffix.edges),
                tie_signature,
            )
            if _better(candidate, best):
                best = candidate
        return best

    return solve((1 << count) - 1)


def match_first_round(participants, tournament_key, policy=None):
    """Return exact Round 1 pairs or a safe signal to retain legacy seeding.

    Zero-score pairs are game-only fallback pairs and carry no discovery label.
    A block is absolute: the solver will never place blocked users together.
    """
    policy = policy or MatchingPolicy()
    if not isinstance(policy, MatchingPolicy):
        raise MatchingInputError('policy must be a MatchingPolicy')
    if not isinstance(tournament_key, (str, int)) or not str(tournament_key).strip():
        raise MatchingInputError('tournament_key is required')
    try:
        snapshots = tuple(participants)
    except TypeError as exc:
        raise MatchingInputError('participants must be iterable') from exc
    if not 2 <= len(snapshots) <= 16:
        raise MatchingInputError('participant count must be between 2 and 16')
    if any(not isinstance(item, ParticipantSnapshot) for item in snapshots):
        raise MatchingInputError('participants must contain ParticipantSnapshot values')
    user_ids = [item.user_id for item in snapshots]
    if len(set(user_ids)) != len(user_ids):
        raise MatchingInputError('participant user IDs must be unique')

    snapshots = tuple(sorted(snapshots, key=lambda item: item.user_id))
    deadline = time.perf_counter() + (policy.timeout_ms / 1000)
    bye = ()
    plan = None
    try:
        if len(snapshots) % 2:
            bye_candidates = sorted(
                snapshots,
                key=lambda item: _tie_value(
                    tournament_key, policy.algorithm_version, item.user_id
                ),
            )
            for bye_candidate in bye_candidates:
                remaining = tuple(
                    item for item in snapshots if item.user_id != bye_candidate.user_id
                )
                plan = _solve_even(remaining, tournament_key, policy, deadline)
                if plan is not None:
                    snapshots = remaining
                    bye = (bye_candidate.user_id,)
                    break
        else:
            plan = _solve_even(snapshots, tournament_key, policy, deadline)
    except MatchingTimeoutError:
        return MatchResult(
            policy.algorithm_version, 'timeout', len(user_ids), (), (), (),
            0, 0, True,
        )

    if time.perf_counter() > deadline:
        return MatchResult(
            policy.algorithm_version, 'timeout', len(user_ids), (), (), (),
            0, 0, True,
        )

    if plan is None:
        return MatchResult(
            policy.algorithm_version, 'constraints_unsatisfied', len(user_ids),
            (), (), bye, 0, 0, True,
        )

    pair_results = []
    for edge in plan.edges:
        first = snapshots[edge.first_index]
        second = snapshots[edge.second_index]
        pair_results.append(PairResult(
            first.user_id,
            second.user_id,
            edge.score,
            edge.score > 0,
            'commercial_match' if edge.score > 0 else 'game_only',
            edge.reasons,
        ))
    pair_results.sort(key=lambda pair: _tie_value(
        tournament_key, policy.algorithm_version, pair.player1_id, pair.player2_id
    ))
    seed_order = tuple(
        user_id
        for pair in pair_results
        for user_id in (pair.player1_id, pair.player2_id)
    ) + bye
    status = 'matched' if plan.hybrid_count else 'no_positive_matches'
    return MatchResult(
        policy.algorithm_version,
        status,
        len(user_ids),
        seed_order,
        tuple(pair_results),
        bye,
        plan.score,
        plan.hybrid_count,
        plan.hybrid_count == 0,
    )
