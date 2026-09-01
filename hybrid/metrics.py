"""Privacy-safe aggregate measurements for the Version 3 MVP pilot."""

from datetime import datetime

from database import (
    DiscoveryMatchAudit,
    DiscoveryProfile,
    DiscoveryReport,
    HybridPilotMetric,
    Player,
    Tournament,
    UserBlock,
    db,
)


ALLOWED_COUNTERS = {
    'chat_messages_delivered',
    'chat_storage_failures',
}


def _percentage(numerator, denominator):
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def increment_pilot_counter(metric_key, amount=1):
    """Best-effort aggregate increment that cannot block the feature it measures."""
    if metric_key not in ALLOWED_COUNTERS:
        return False
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return False
    if amount <= 0:
        return False
    try:
        metric = HybridPilotMetric.query.filter_by(metric_key=metric_key).first()
        if metric is None:
            metric = HybridPilotMetric(metric_key=metric_key, total_count=0)
            db.session.add(metric)
        metric.total_count += amount
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def pilot_metrics_snapshot():
    """Return aggregate counts and rates without personal or message-level data."""
    profiles = DiscoveryProfile.query.all()
    enabled_profiles = [profile for profile in profiles if profile.is_enabled]
    complete_profiles = [
        profile for profile in enabled_profiles
        if profile.intent
        and profile.category
        and profile.location
        and (profile.predefined_caption or profile.custom_caption)
    ]
    player_accounts = Player.query.count()

    audits = DiscoveryMatchAudit.query.all()
    possible_pairs = sum(max(0, audit.participant_count // 2) for audit in audits)
    relevant_pairs = sum(max(0, audit.hybrid_pair_count) for audit in audits)
    fallback_audits = sum(
        1 for audit in audits if audit.legacy_fallback_recommended
    )
    durations = [
        float(audit.matching_duration_ms) for audit in audits
        if audit.matching_duration_ms is not None
    ]

    ordinary_tournaments = Tournament.query.filter(
        Tournament.tournament_type != 'cup'
    ).all()
    started_tournaments = [
        tournament for tournament in ordinary_tournaments
        if tournament.status in ('locked', 'in_progress', 'completed')
        or tournament.started_at is not None
    ]
    completed_tournaments = [
        tournament for tournament in ordinary_tournaments
        if tournament.status == 'completed' or tournament.completed_at is not None
    ]

    counter_rows = {
        metric.metric_key: metric.total_count
        for metric in HybridPilotMetric.query.filter(
            HybridPilotMetric.metric_key.in_(ALLOWED_COUNTERS)
        ).all()
    }
    reports_total = DiscoveryReport.query.count()
    pending_reports = DiscoveryReport.query.filter(
        DiscoveryReport.status.in_(('pending', 'in_review'))
    ).count()

    return {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'scope': 'All recorded local and invited pilot activity',
        'privacy_note': (
            'Aggregate counts only. No captions, message bodies, contact details '
            'or raw matching preferences are included.'
        ),
        'adoption': {
            'player_accounts': player_accounts,
            'profiles_created': len(profiles),
            'profiles_enabled': len(enabled_profiles),
            'profiles_complete': len(complete_profiles),
            'opt_in_rate_pct': _percentage(len(enabled_profiles), player_accounts),
            'profile_completion_rate_pct': _percentage(
                len(complete_profiles), len(enabled_profiles)
            ),
        },
        'matching': {
            'audit_runs': len(audits),
            'participant_observations': sum(audit.participant_count for audit in audits),
            'possible_pairs': possible_pairs,
            'relevant_pairs': relevant_pairs,
            'game_only_pairs': max(0, possible_pairs - relevant_pairs),
            'relevant_pair_rate_pct': _percentage(relevant_pairs, possible_pairs),
            'fallback_audits': fallback_audits,
            'fallback_rate_pct': _percentage(fallback_audits, len(audits)),
            'average_latency_ms': round(sum(durations) / len(durations), 3) if durations else None,
            'maximum_latency_ms': round(max(durations), 3) if durations else None,
        },
        'qmessanger': {
            'messages_delivered': counter_rows.get('chat_messages_delivered', 0),
            'storage_failures': counter_rows.get('chat_storage_failures', 0),
        },
        'safety': {
            'active_blocks': UserBlock.query.filter_by(is_active=True).count(),
            'reports_total': reports_total,
            'reports_awaiting_action': pending_reports,
        },
        'tournaments': {
            'ordinary_total': len(ordinary_tournaments),
            'ordinary_started': len(started_tournaments),
            'ordinary_completed': len(completed_tournaments),
            'completion_rate_pct': _percentage(
                len(completed_tournaments), len(started_tournaments)
            ),
        },
    }
