"""Privacy-safe Hybrid+ relevance across eligible open brackets."""

from sqlalchemy import or_

from database import (
    DiscoveryProfile,
    Tournament,
    TournamentParticipant,
    UserBlock,
    db,
)
from pricing.service import has_plan_level


ORDINARY_TYPES = ('standard', 'premium', 'deluxe')


def _moderation_safe(profile):
    return bool(
        profile
        and profile.is_enabled
        and profile.is_visible
        and (
            not profile.custom_caption
            or profile.moderation_status == 'approved'
        )
    )


def open_bracket_relevance(user_id, config):
    """Return relevance badges without identities, captions or preferences."""
    if not (
        config.get('HYBRID_ENABLED')
        and config.get('HYBRID_PROFILE_ENABLED')
        and config.get('HYBRID_BRACKET_DISCOVERY_ENABLED')
        and config.get('PRICING_ENABLED')
        and config.get('PRICING_HYBRID_PLUS_ENABLED')
        and has_plan_level(user_id, 'hybrid_plus')
    ):
        return None
    requester = DiscoveryProfile.query.filter_by(user_id=user_id).first()
    if not _moderation_safe(requester) or requester.intent != 'selling':
        return []

    blocked_ids = set()
    for block in UserBlock.query.filter(
        UserBlock.is_active.is_(True),
        or_(UserBlock.blocker_id == user_id, UserBlock.blocked_id == user_id),
    ).all():
        blocked_ids.add(
            block.blocked_id if block.blocker_id == user_id else block.blocker_id
        )

    joined_ids = {
        row.tournament_id
        for row in TournamentParticipant.query.filter_by(
            user_id=user_id, status='registered'
        ).all()
    }
    tournaments = Tournament.query.filter(
        Tournament.status == 'open',
        Tournament.tournament_type.in_(ORDINARY_TYPES),
    ).order_by(Tournament.created_at.asc(), Tournament.id.asc()).all()

    results = []
    for tournament in tournaments:
        if tournament.id in joined_ids:
            continue
        participant_ids = [
            row.user_id
            for row in TournamentParticipant.query.filter_by(
                tournament_id=tournament.id, status='registered'
            ).all()
            if row.user_id not in blocked_ids
        ]
        if not participant_ids:
            continue
        candidates = DiscoveryProfile.query.filter(
            DiscoveryProfile.user_id.in_(participant_ids),
            DiscoveryProfile.intent == 'seeking',
            DiscoveryProfile.category == requester.category,
        ).all()
        candidates = [profile for profile in candidates if _moderation_safe(profile)]
        if not candidates:
            continue
        boosted = bool(
            requester.subcategory
            and any(
                profile.subcategory == requester.subcategory
                for profile in candidates
            )
        )
        results.append({
            'tournament_id': tournament.id,
            'tournament_code': tournament.tournament_code,
            'relevance': 'boosted' if boosted else 'possible',
            'badge': 'Potential seeker',
            'label': 'Potential relevant match, subject to available participants',
        })
    return sorted(
        results,
        key=lambda row: (
            0 if row['relevance'] == 'boosted' else 1,
            row['tournament_id'],
        ),
    )
