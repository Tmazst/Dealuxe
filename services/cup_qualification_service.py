"""Idempotent uMshova Cup qualification recording."""

from database import CupQualification, db


ACTIVE_QUALIFICATION_STATUSES = {'qualified', 'checked_in'}


def award_cup_qualification(tournament, user_id, event_key, season):
    """Record a tournament win and grant at most one active event seat."""
    existing_source = CupQualification.query.filter_by(
        source_tournament_id=tournament.id
    ).first()
    if existing_source is not None:
        return existing_source, False

    active = CupQualification.query.filter(
        CupQualification.user_id == user_id,
        CupQualification.event_key == event_key,
        CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
    ).first()
    has_active_seat = active is None
    qualification = CupQualification(
        source_tournament_id=tournament.id,
        user_id=user_id,
        season=season,
        event_key=event_key,
        status='qualified' if has_active_seat else 'duplicate_win',
        seat_key=f'{event_key}:{user_id}' if has_active_seat else None,
        notes=(
            'Active Cup seat awarded from Position 1.'
            if has_active_seat
            else f'Additional qualifying win; active seat retained from tournament #{active.source_tournament_id}.'
        ),
    )
    db.session.add(qualification)
    db.session.flush()
    return qualification, has_active_seat


def qualification_summary(user_id, event_key=None):
    query = CupQualification.query.filter_by(user_id=user_id)
    if event_key:
        query = query.filter_by(event_key=event_key)
    records = query.order_by(CupQualification.qualified_at.desc()).all()
    active = next(
        (record for record in records if record.status in ACTIVE_QUALIFICATION_STATUSES),
        None,
    )
    return {
        'qualified': active is not None,
        'active': active.to_dict() if active else None,
        'qualifying_wins': len(records),
        'records': [record.to_dict() for record in records],
    }
