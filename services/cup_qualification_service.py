"""Idempotent uMshova Cup qualification and allocated-seat recording."""

import json

from database import CupQualification, Tournament, TournamentParticipant, db


ACTIVE_QUALIFICATION_STATUSES = {'qualified', 'checked_in'}


def _event_key(tournament):
    try:
        notes = json.loads(tournament.notes or '{}')
    except (TypeError, ValueError):
        notes = {}
    return str(notes.get('event_key') or '').strip()


def _open_allocated_cup(event_key):
    for cup in Tournament.query.filter_by(
        tournament_type='cup', status='open', cup_creation_mode='empty'
    ).order_by(Tournament.id.asc()).all():
        if _event_key(cup) == event_key:
            return cup
    return None


def _attach_to_cup(qualification, cup):
    qualification.target_cup_tournament_id = cup.id
    qualification.seat_source = qualification.seat_source or 'bracket_winner'
    existing = TournamentParticipant.query.filter_by(
        tournament_id=cup.id, user_id=qualification.user_id
    ).first()
    if existing is None:
        db.session.add(TournamentParticipant(
            tournament_id=cup.id,
            user_id=qualification.user_id,
            status='registered',
            payment_status='completed',
            paid_amount=0.0,
            payment_method='cup_qualification',
            notes='Cup qualification #{0} · {1}'.format(
                qualification.id or 'pending', qualification.seat_source
            ),
        ))
        cup.current_player_count = int(cup.current_player_count or 0) + 1


def award_cup_qualification(tournament, user_id, event_key, season, capacity=64):
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
    target_cup = _open_allocated_cup(event_key)
    if target_cup is not None:
        capacity = int(target_cup.cup_qualifier_seats or 0)
        active_seat_count = CupQualification.query.filter(
            CupQualification.target_cup_tournament_id == target_cup.id,
            CupQualification.seat_source == 'bracket_winner',
            CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
        ).count()
    else:
        active_seat_count = CupQualification.query.filter(
            CupQualification.event_key == event_key,
            CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
        ).count()
    has_active_seat = active is None and active_seat_count < int(capacity)
    if active is not None:
        status = 'duplicate_win'
    elif has_active_seat:
        status = 'qualified'
    else:
        status = 'reserve'
    qualification = CupQualification(
        source_tournament_id=tournament.id,
        user_id=user_id,
        season=season,
        event_key=event_key,
        status=status,
        seat_key=f'{event_key}:{user_id}' if has_active_seat else None,
        target_cup_tournament_id=target_cup.id if has_active_seat and target_cup else None,
        seat_source='bracket_winner',
        notes=(
            'Active Cup seat awarded from Position 1.'
            if has_active_seat
            else (
                f'Additional qualifying win; active seat retained from tournament #{active.source_tournament_id}.'
                if active is not None
                else f'Cup capacity of {capacity} reached; qualifier added to reserves.'
            )
        ),
    )
    db.session.add(qualification)
    db.session.flush()
    if has_active_seat and target_cup is not None:
        _attach_to_cup(qualification, target_cup)
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
