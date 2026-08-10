from datetime import datetime

from database import (
    db,
    Tournament,
    TournamentMatch,
    TournamentParticipant,
    User,
    get_player_by_user_id,
)
from sqlalchemy import or_


def _serialize_user(user):
    player = get_player_by_user_id(user.id)
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'phone': user.phone,
        'full_name': user.full_name,
        'is_active': user.is_active,
        'is_admin': user.is_admin,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'real_balance': player.real_balance if player else None,
        'fake_balance': player.fake_balance if player else None,
    }


def _coerce_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def list_users(search=''):
    query = User.query.order_by(User.created_at.desc())
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(search_term),
                User.email.ilike(search_term),
            )
        )
    return [_serialize_user(user) for user in query.all()]


def update_user(user_id, data):
    target_user = User.query.get_or_404(user_id)
    player = get_player_by_user_id(target_user.id)

    if 'is_active' in data:
        target_user.is_active = _coerce_bool(data['is_active'])

    if 'is_admin' in data:
        target_user.is_admin = _coerce_bool(data['is_admin'])

    if player is None and any(field in data for field in ('real_balance', 'fake_balance')):
        raise ValueError('Associated player profile not found')

    for field in ('real_balance', 'fake_balance'):
        if field in data:
            try:
                setattr(player, field, float(data[field]))
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Invalid value for {field}') from exc

    db.session.commit()
    return _serialize_user(target_user)


def list_tournaments():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return [
        {
            'id': tournament.id,
            'tournament_code': tournament.tournament_code,
            'tournament_name': tournament.tournament_name,
            'tournament_type': tournament.tournament_type,
            'status': tournament.status,
            'entry_fee': tournament.entry_fee,
            'prize_pool_amount': tournament.prize_pool_amount,
            'current_player_count': tournament.current_player_count,
            'max_players': tournament.max_players,
            'creator_id': tournament.creator_id,
            'locked_at': tournament.locked_at.isoformat() if tournament.locked_at else None,
            'started_at': tournament.started_at.isoformat() if tournament.started_at else None,
            'completed_at': tournament.completed_at.isoformat() if tournament.completed_at else None,
        }
        for tournament in tournaments
    ]


def cancel_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.status = 'cancelled'
    tournament.completed_at = tournament.completed_at or datetime.utcnow()

    participants = TournamentParticipant.query.filter_by(tournament_id=tournament.id).all()
    for participant in participants:
        participant.status = 'eliminated'

    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).all()
    for match in matches:
        if match.status != 'completed':
            match.status = 'cancelled'

    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def lock_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.status = 'locked'
    tournament.locked_at = tournament.locked_at or datetime.utcnow()
    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def start_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.status = 'in_progress'
    tournament.started_at = tournament.started_at or datetime.utcnow()
    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def dashboard_summary():
    return {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'total_tournaments': Tournament.query.count(),
        'open_tournaments': Tournament.query.filter_by(status='open').count(),
        'in_progress_tournaments': Tournament.query.filter_by(status='in_progress').count(),
    }
