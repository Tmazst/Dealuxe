"""Database adapter for observing matcher decisions without changing brackets."""

from datetime import datetime
import json
import time

from sqlalchemy import or_

from database import (
    DiscoveryMatchAudit,
    DiscoveryProfile,
    User,
    UserBlock,
    db,
)
from hybrid.matching import MatchingPolicy, ParticipantSnapshot, match_first_round


ORDINARY_TOURNAMENT_TYPES = frozenset({'standard', 'premium', 'deluxe'})
REASON_LABELS = {
    'complementary_intent': 'Seller and seeker complement each other',
    'collaboration_fit': 'Both are open to collaboration',
    'collaboration_open': 'Collaboration preference is compatible',
    'category_match': 'Same category',
    'subcategory_match': 'Same item or service',
    'location_match': 'Same location',
    'plan_level': 'Compatible discovery access',
}


def shadow_mode_enabled(config):
    return bool(
        config.get('HYBRID_ENABLED', False)
        and config.get('HYBRID_PROFILE_ENABLED', False)
        and config.get('HYBRID_MATCHING_SHADOW_ENABLED', False)
        and not config.get('HYBRID_MATCHING_ENABLED', False)
    )


def _json(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


def _load_json(value, fallback):
    try:
        return json.loads(value or '')
    except (TypeError, ValueError):
        return fallback


def build_participant_snapshots(user_ids):
    """Capture only the structured, non-caption fields required by the matcher."""
    ordered_ids = tuple(dict.fromkeys(int(user_id) for user_id in user_ids))
    users = {
        user.id: user
        for user in User.query.filter(User.id.in_(ordered_ids)).all()
    }
    profiles = {
        profile.user_id: profile
        for profile in DiscoveryProfile.query.filter(
            DiscoveryProfile.user_id.in_(ordered_ids)
        ).all()
    }
    blocks_by_user = {user_id: set() for user_id in ordered_ids}
    blocks = UserBlock.query.filter(
        UserBlock.is_active.is_(True),
        or_(
            UserBlock.blocker_id.in_(ordered_ids),
            UserBlock.blocked_id.in_(ordered_ids),
        ),
    ).all()
    participant_ids = set(ordered_ids)
    for block in blocks:
        if block.blocker_id in participant_ids and block.blocked_id in participant_ids:
            blocks_by_user[block.blocker_id].add(block.blocked_id)
            blocks_by_user[block.blocked_id].add(block.blocker_id)

    snapshots = []
    for user_id in ordered_ids:
        user = users.get(user_id)
        if user is None:
            raise LookupError(f'Tournament participant user {user_id} was not found')
        profile = profiles.get(user_id)
        profile_enabled = bool(profile and profile.is_enabled)
        snapshots.append(ParticipantSnapshot(
            user_id=user_id,
            profile_enabled=profile_enabled,
            # Version 3 pilot profiles receive temporary no-payment access.
            entitlement_active=profile_enabled,
            suspended=not bool(user.is_active),
            is_visible=bool(profile and profile.is_visible),
            moderation_status=(
                profile.moderation_status if profile else 'not_required'
            ),
            intent=profile.intent if profile else None,
            category=profile.category if profile else None,
            subcategory=profile.subcategory if profile else None,
            location=profile.location if profile else None,
            plan_level=0,
            blocked_user_ids=frozenset(blocks_by_user[user_id]),
        ))
    return tuple(snapshots)


def record_shadow_audit(tournament, participant_user_ids, legacy_seed_order, config):
    """Run and persist a preview; never mutate TournamentBracket or matches."""
    if not shadow_mode_enabled(config):
        return None
    if tournament.tournament_type not in ORDINARY_TOURNAMENT_TYPES:
        return None
    result, matching_duration_ms = evaluate_matching(
        tournament, participant_user_ids, config
    )
    return persist_match_audit(
        tournament, result, legacy_seed_order, 'shadow', matching_duration_ms
    )


def evaluate_matching(tournament, participant_user_ids, config):
    """Evaluate one deterministic proposal without mutating tournament state."""
    snapshots = build_participant_snapshots(participant_user_ids)
    policy = MatchingPolicy(
        timeout_ms=int(config.get('HYBRID_MATCHING_TIMEOUT_MS', 250))
    )
    started_at = time.perf_counter()
    result = match_first_round(
        snapshots,
        tournament_key=tournament.id,
        policy=policy,
    )
    matching_duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
    return result, matching_duration_ms


def persist_match_audit(tournament, result, legacy_seed_order, mode, matching_duration_ms):
    """Persist a completed shadow/live decision after the bracket commit boundary."""
    audit = DiscoveryMatchAudit.query.filter_by(
        tournament_id=tournament.id,
        mode=mode,
        algorithm_version=result.algorithm_version,
    ).first()
    if audit is None:
        audit = DiscoveryMatchAudit(
            tournament_id=tournament.id,
            mode=mode,
            algorithm_version=result.algorithm_version,
        )
        db.session.add(audit)
    audit.status = result.status
    audit.participant_count = result.participant_count
    audit.total_score = result.total_score
    audit.hybrid_pair_count = result.hybrid_pair_count
    audit.matching_duration_ms = matching_duration_ms
    audit.legacy_fallback_recommended = result.legacy_fallback_recommended
    audit.proposed_seed_order_json = _json(list(result.seed_order))
    audit.legacy_seed_order_json = _json(list(legacy_seed_order))
    audit.pairs_json = _json([pair.to_dict() for pair in result.pairs])
    audit.updated_at = datetime.utcnow()
    db.session.commit()
    return serialize_match_audit(audit)


def _seed_pairs(seed_order):
    seed_order = list(seed_order or ())
    return [
        (seed_order[index], seed_order[index + 1] if index + 1 < len(seed_order) else None)
        for index in range(0, len(seed_order), 2)
    ]


def _pair_key(first_id, second_id):
    return tuple(sorted(
        user_id for user_id in (first_id, second_id) if user_id is not None
    ))


def _player_name(user_id, usernames):
    if user_id is None:
        return 'Bye'
    return usernames.get(user_id) or f'Player #{user_id}'


def _comparison_payload(legacy_seed, pairs, usernames):
    legacy_pairs = _seed_pairs(legacy_seed)
    legacy_keys = {_pair_key(*pair) for pair in legacy_pairs}
    proposed_keys = {
        _pair_key(pair.get('player1_id'), pair.get('player2_id'))
        for pair in pairs
    }

    readable_legacy = []
    for first_id, second_id in legacy_pairs:
        pair_key = _pair_key(first_id, second_id)
        readable_legacy.append({
            'player1_id': first_id,
            'player1_username': _player_name(first_id, usernames),
            'player2_id': second_id,
            'player2_username': _player_name(second_id, usernames),
            'comparison_status': (
                'same_as_proposed' if pair_key in proposed_keys else 'changed_in_proposal'
            ),
        })

    readable_proposed = []
    for pair in pairs:
        first_id = pair.get('player1_id')
        second_id = pair.get('player2_id')
        reason_codes = list(pair.get('reason_codes') or ())
        readable_proposed.append({
            **pair,
            'player1_username': _player_name(first_id, usernames),
            'player2_username': _player_name(second_id, usernames),
            'pair_label_display': (
                'Commercial match'
                if pair.get('hybrid_match')
                else 'Game only'
            ),
            'reason_labels': [
                REASON_LABELS.get(code, code.replace('_', ' ').title())
                for code in reason_codes
            ],
            'comparison_status': (
                'same_as_live'
                if _pair_key(first_id, second_id) in legacy_keys
                else 'changed_from_live'
            ),
        })
    return {
        'legacy_pairs': readable_legacy,
        'proposed_pairs': readable_proposed,
        'pairing_changed': legacy_keys != proposed_keys,
    }


def serialize_match_audit(audit, usernames=None):
    legacy_seed = _load_json(audit.legacy_seed_order_json, [])
    proposed_seed = _load_json(audit.proposed_seed_order_json, [])
    pairs = _load_json(audit.pairs_json, [])
    if usernames is None:
        participant_ids = {
            int(user_id)
            for user_id in (*legacy_seed, *proposed_seed)
            if user_id is not None
        }
        usernames = {
            user.id: user.username
            for user in User.query.filter(User.id.in_(participant_ids)).all()
        } if participant_ids else {}
    comparison = _comparison_payload(legacy_seed, pairs, usernames)
    return {
        'id': audit.id,
        'tournament_id': audit.tournament_id,
        'tournament_name': audit.tournament.tournament_name if audit.tournament else None,
        'tournament_type': audit.tournament.tournament_type if audit.tournament else None,
        'mode': audit.mode,
        'algorithm_version': audit.algorithm_version,
        'status': audit.status,
        'participant_count': audit.participant_count,
        'total_score': audit.total_score,
        'hybrid_pair_count': audit.hybrid_pair_count,
        'matching_duration_ms': audit.matching_duration_ms,
        'legacy_fallback_recommended': bool(audit.legacy_fallback_recommended),
        'proposed_seed_order': proposed_seed,
        'legacy_seed_order': legacy_seed,
        'pairs': pairs,
        **comparison,
        'created_at': audit.created_at.isoformat() if audit.created_at else None,
        'updated_at': audit.updated_at.isoformat() if audit.updated_at else None,
    }


def list_match_audits(limit=100):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError('limit must be an integer')
    if not 1 <= limit <= 500:
        raise ValueError('limit must be between 1 and 500')
    audits = DiscoveryMatchAudit.query.order_by(
        DiscoveryMatchAudit.created_at.desc(), DiscoveryMatchAudit.id.desc()
    ).limit(limit).all()
    participant_ids = set()
    for audit in audits:
        participant_ids.update(
            user_id
            for user_id in _load_json(audit.legacy_seed_order_json, [])
            if user_id is not None
        )
        participant_ids.update(
            user_id
            for user_id in _load_json(audit.proposed_seed_order_json, [])
            if user_id is not None
        )
    usernames = {
        user.id: user.username
        for user in User.query.filter(User.id.in_(participant_ids)).all()
    } if participant_ids else {}
    return [serialize_match_audit(audit, usernames=usernames) for audit in audits]
