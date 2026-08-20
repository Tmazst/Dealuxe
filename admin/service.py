from datetime import datetime

from flask import current_app

from database import (
    db,
    Tournament,
    TournamentMatch,
    TournamentParticipant,
    TournamentBracket,
    User,
    Player,
    AdminAuditLog,
    Dispute,
    WalletAdjustment,
    add_tournament_participant,
    create_tournament_record,
    get_player_by_user_id,
)
from sqlalchemy import or_


def log_admin_action(admin_user_id, action, entity_type=None, entity_id=None, summary=None, details=None):
    """Persist an immutable audit entry for an admin action."""
    db.session.add(AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details=details,
    ))


def _username(user_id):
    if not user_id:
        return None
    user = User.query.get(user_id)
    return user.username if user else None


def _serialize_user(user):
    player = get_player_by_user_id(user.id)
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'phone': user.phone,
        'full_name': user.full_name,
        'country': user.country,
        'kyc_status': user.kyc_status or 'not_submitted',
        'kyc_document_path': user.kyc_document_path,
        'id_photo_path': user.id_photo_path,
        'id_photo_back_path': user.id_photo_back_path,
        'is_active': user.is_active,
        'is_admin': user.is_admin,
        'is_super_admin': user.is_super_admin,
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


def update_user(user_id, data, admin_user_id=None):
    target_user = User.query.get_or_404(user_id)
    player = get_player_by_user_id(target_user.id)

    # NOTE: `is_admin` / `is_super_admin` are intentionally NOT settable here.
    # Admin roles are managed exclusively via the super admin CLI
    # (`python super_admin_cli.py assign/revoke`).

    changes = []
    if 'is_active' in data:
        target_user.is_active = _coerce_bool(data['is_active'])
        changes.append(f"is_active={target_user.is_active}")

    if player is None and any(field in data for field in ('real_balance', 'fake_balance')):
        raise ValueError('Associated player profile not found')

    for field in ('real_balance', 'fake_balance'):
        if field in data:
            try:
                setattr(player, field, float(data[field]))
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Invalid value for {field}') from exc
            changes.append(f"{field}={data[field]}")

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'user.update',
            entity_type='user', entity_id=user_id,
            summary='; '.join(changes) if changes else 'no fields changed',
        )

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


def cancel_tournament(tournament_id, admin_user_id=None):
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

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'tournament.cancel',
            entity_type='tournament', entity_id=tournament.id,
            summary=f"Cancelled tournament '{tournament.tournament_name}'",
        )

    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def lock_tournament(tournament_id, admin_user_id=None):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.status = 'locked'
    tournament.locked_at = tournament.locked_at or datetime.utcnow()

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'tournament.lock',
            entity_type='tournament', entity_id=tournament.id,
            summary=f"Locked tournament '{tournament.tournament_name}'",
        )

    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def start_tournament(tournament_id, admin_user_id=None):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.status = 'in_progress'
    tournament.started_at = tournament.started_at or datetime.utcnow()

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'tournament.start',
            entity_type='tournament', entity_id=tournament.id,
            summary=f"Started tournament '{tournament.tournament_name}'",
        )

    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def force_start(tournament_id, admin_user_id=None):
    """Force a locked/open tournament into in_progress and build its bracket if missing."""
    tournament = Tournament.query.get_or_404(tournament_id)
    if tournament.status in ('completed', 'cancelled'):
        raise ValueError('Tournament is already completed or cancelled')

    if tournament.status != 'in_progress' and not TournamentBracket.query.filter_by(tournament_id=tournament.id).first():
        from controllers.tournament_controller import _build_bracket
        tournament.status = 'locked'
        tournament.locked_at = tournament.locked_at or datetime.utcnow()
        tournament.locked_player_count = tournament.locked_player_count or tournament.current_player_count
        _build_bracket(tournament)

    tournament.status = 'in_progress'
    tournament.started_at = tournament.started_at or datetime.utcnow()

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'tournament.force_start',
            entity_type='tournament', entity_id=tournament.id,
            summary=f"Force-started tournament '{tournament.tournament_name}'",
        )

    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def complete_tournament(tournament_id, admin_user_id=None):
    """Admin force-completes a tournament (no prize auto-award)."""
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.status = 'completed'
    tournament.completed_at = tournament.completed_at or datetime.utcnow()

    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).all()
    for match in matches:
        if match.status not in ('completed', 'cancelled'):
            match.status = 'cancelled'

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'tournament.complete',
            entity_type='tournament', entity_id=tournament.id,
            summary=f"Force-completed tournament '{tournament.tournament_name}'",
        )

    db.session.commit()
    return {'tournament_id': tournament.id, 'status': tournament.status}


def dashboard_summary():
    from database import AdminAuditLog, Dispute
    return {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'total_tournaments': Tournament.query.count(),
        'open_tournaments': Tournament.query.filter_by(status='open').count(),
        'in_progress_tournaments': Tournament.query.filter_by(status='in_progress').count(),
        'pending_disputes': Dispute.query.filter_by(status='pending').count(),
        'total_credits_awarded': round(
            db.session.query(db.func.coalesce(db.func.sum(WalletAdjustment.delta), 0))
            .filter(WalletAdjustment.delta > 0).scalar() or 0, 2
        ),
        'recent_audit_actions': AdminAuditLog.query.count(),
    }


def get_tournament_detail(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).order_by(TournamentMatch.id).all()
    participants = TournamentParticipant.query.filter_by(tournament_id=tournament.id).all()

    fixtures = []
    for match in matches:
        bracket = TournamentBracket.query.get(match.bracket_id) if match.bracket_id else None
        fixtures.append({
            'id': match.id,
            'round_name': bracket.round_name if bracket else None,
            'player1_id': match.player1_id,
            'player1_name': _username(match.player1_id),
            'player2_id': match.player2_id,
            'player2_name': _username(match.player2_id),
            'status': match.status,
            'winner_id': match.winner_id,
            'game_room_id': match.game_room_id,
        })

    return {
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
        'creator_name': _username(tournament.creator_id),
        'locked_at': tournament.locked_at.isoformat() if tournament.locked_at else None,
        'started_at': tournament.started_at.isoformat() if tournament.started_at else None,
        'completed_at': tournament.completed_at.isoformat() if tournament.completed_at else None,
        'participants': [
            {
                'user_id': p.user_id,
                'username': _username(p.user_id),
                'status': p.status,
                'payment_status': p.payment_status,
            }
            for p in participants
        ],
        'fixtures': fixtures,
    }


def list_audit_logs(limit=100):
    logs = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            'id': log.id,
            'admin_user_id': log.admin_user_id,
            'admin_username': _username(log.admin_user_id),
            'action': log.action,
            'entity_type': log.entity_type,
            'entity_id': log.entity_id,
            'summary': log.summary,
            'details': log.details,
            'created_at': log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# -----------------------------
# WALLET CONTROLS
# -----------------------------

def adjust_wallet(admin_user_id, user_id, balance_type, delta, reason):
    """Adjust a player's real/fake balance with an audit reason (credits or debits)."""
    if balance_type not in ('real', 'fake'):
        raise ValueError('balance_type must be "real" or "fake"')
    delta = float(delta)
    if delta == 0:
        raise ValueError('delta must be non-zero')
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required for wallet adjustments')

    player = get_player_by_user_id(user_id)
    if player is None:
        raise ValueError('Player profile not found')

    current = player.real_balance if balance_type == 'real' else player.fake_balance
    new_balance = round(current + delta, 2)
    if new_balance < 0:
        raise ValueError(f'Adjustment would make the balance negative ({new_balance:.2f})')

    if balance_type == 'real':
        player.real_balance = new_balance
    else:
        player.fake_balance = new_balance

    db.session.add(WalletAdjustment(
        user_id=user_id,
        balance_type=balance_type,
        delta=round(delta, 2),
        reason=reason,
        admin_user_id=admin_user_id,
    ))
    log_admin_action(
        admin_user_id, 'wallet.adjust',
        entity_type='wallet', entity_id=user_id,
        summary=f'{balance_type} balance adjusted by {delta:+.2f} (new: {new_balance:.2f})',
        details=reason,
    )
    db.session.commit()
    return {'user_id': user_id, 'balance_type': balance_type, 'new_balance': new_balance}


def award_credits(admin_user_id, user_id, amount, balance_type='fake', reason='Free credits awarded'):
    """Award free credits / promotional funds to a player's wallet."""
    if float(amount) <= 0:
        raise ValueError('amount must be positive')
    return adjust_wallet(
        admin_user_id, user_id, balance_type, float(amount),
        reason or 'Free credits awarded',
    )


# -----------------------------
# DISPUTES
# -----------------------------

DISPUTE_CATEGORIES = ('payment', 'result', 'account', 'other')


def _serialize_dispute(dispute):
    return {
        'id': dispute.id,
        'user_id': dispute.user_id,
        'username': _username(dispute.user_id),
        'tournament_id': dispute.tournament_id,
        'match_id': dispute.match_id,
        'category': dispute.category,
        'description': dispute.description,
        'status': dispute.status,
        'resolution': dispute.resolution,
        'resolved_by': dispute.resolved_by,
        'resolved_by_username': _username(dispute.resolved_by),
        'resolved_at': dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        'created_at': dispute.created_at.isoformat() if dispute.created_at else None,
    }


def create_dispute(user_id, data):
    category = (data.get('category') or 'other').strip().lower()
    if category not in DISPUTE_CATEGORIES:
        raise ValueError('Invalid dispute category')
    description = (data.get('description') or '').strip()
    if not description:
        raise ValueError('A description is required')

    dispute = Dispute(
        user_id=user_id,
        tournament_id=data.get('tournament_id'),
        match_id=data.get('match_id'),
        category=category,
        description=description,
    )
    db.session.add(dispute)
    db.session.commit()
    return _serialize_dispute(dispute)


def list_disputes(status=''):
    query = Dispute.query.order_by(Dispute.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    return [_serialize_dispute(dispute) for dispute in query.all()]


def resolve_dispute(dispute_id, admin_user_id, status='resolved', resolution=None):
    if status not in ('resolved', 'rejected', 'in_review'):
        raise ValueError('status must be resolved, rejected, or in_review')
    resolution = (resolution or '').strip()
    if status != 'in_review' and not resolution:
        raise ValueError('A resolution note is required')

    dispute = Dispute.query.get_or_404(dispute_id)
    dispute.status = status
    if status == 'in_review':
        dispute.resolution = dispute.resolution or resolution or None
    else:
        dispute.resolution = resolution
        dispute.resolved_by = admin_user_id
        dispute.resolved_at = datetime.utcnow()

    log_admin_action(
        admin_user_id, f'dispute.{status}',
        entity_type='dispute', entity_id=dispute.id,
        summary=f'Dispute {dispute.id} marked {status}',
        details=resolution,
    )
    db.session.commit()
    return _serialize_dispute(dispute)


# -----------------------------
# TEST ARENA (admin-only test tournament: 1 manual player + 3 bots)
# -----------------------------

TEST_BOT_NAMES = ('tournament_bot_1', 'tournament_bot_2', 'tournament_bot_3')
TEST_BOT_PASSWORD = 'TournamentTest!2026'


def _get_or_create_test_player(username, email):
    """Get or create a local-test player account with a funded wallet."""
    from database import get_user_by_username
    user = get_user_by_username(username)
    created = user is None
    if created:
        user = User(username=username, email=email)
        user.set_password(TEST_BOT_PASSWORD)
        db.session.add(user)
        db.session.flush()
    if Player.query.filter_by(user_id=user.id).first() is None:
        db.session.add(Player(user_id=user.id, real_balance=1000.0))
    return user, created


def create_test_tournament(admin_user_id=None, manual_username='tournament_tester'):
    """Create a local test tournament: one manual player + three bots.

    Shares a single code path with ``tools/seed_manual_bot_tournament.py`` so
    the admin UI and the CLI behave identically. Uses local-test participants
    (no external payments) and mirrors ``test_tournament_match_flow.py``: lock
    → build bracket → pre-settle the bot-vs-bot semi-final → the manual player
    immediately has a real scheduled match against a bot.
    """
    from controllers.tournament_controller import (
        _build_bracket,
        _ensure_prize_pool,
        record_tournament_match_result,
    )

    manual_username = (manual_username or 'tournament_tester').strip()
    if len(manual_username) < 3:
        raise ValueError('A valid manual username is required (min 3 characters)')

    manual, manual_created = _get_or_create_test_player(manual_username, f'{manual_username}@local.test')
    bots = []
    for name in TEST_BOT_NAMES:
        bot, _ = _get_or_create_test_player(name, f'{name}@local.test')
        bots.append(bot)
    db.session.commit()

    tournament = create_tournament_record(
        creator_id=manual.id,
        tournament_type='standard',
        tournament_name=f'Test Arena {datetime.utcnow():%d %b %H:%M}',
        entry_fee=10.0,
        max_players=4,
        is_auto_lock=False,
    )
    for user in [manual, *bots]:
        participant = add_tournament_participant(
            tournament.id, user.id,
            payment_status='completed',
            paid_amount=tournament.entry_fee,
            payment_method='local-test',
        )
        participant.status = 'registered'
        participant.payment_completed_at = datetime.utcnow()

    tournament.current_player_count = 4
    tournament.prize_pool_amount = 40.0
    tournament.status = 'locked'
    tournament.locked_at = datetime.utcnow()
    tournament.locked_player_count = 4
    _ensure_prize_pool(tournament)
    _build_bracket(tournament)
    db.session.commit()

    # Pre-settle the bot-vs-bot semi-final so the manual player has a real match.
    scheduled = TournamentMatch.query.filter_by(
        tournament_id=tournament.id, status='scheduled'
    ).all()
    for match in scheduled:
        if manual.id not in {match.player1_id, match.player2_id}:
            record_tournament_match_result(
                match.id, match.player1_id, match.player2_id,
                win_type='test_bot_simulation', duration_seconds=1,
            )

    next_match = TournamentMatch.query.filter_by(
        tournament_id=tournament.id, status='scheduled'
    ).filter(
        or_(
            TournamentMatch.player1_id == manual.id,
            TournamentMatch.player2_id == manual.id,
        )
    ).first()

    if admin_user_id:
        log_admin_action(
            admin_user_id, 'test_tournament.create',
            entity_type='tournament', entity_id=tournament.id,
            summary=f"Created test arena '{tournament.tournament_name}' (manual: {manual_username})",
        )
    db.session.commit()

    return {
        'tournament_id': tournament.id,
        'tournament_name': tournament.tournament_name,
        'tournament_code': tournament.tournament_code,
        'bracket_url': f'/tournaments/{tournament.id}/bracket',
        'manual_username': manual_username,
        'manual_created': manual_created,
        'manual_password': TEST_BOT_PASSWORD if manual_created else None,
        'bots_enabled': bool(current_app.config.get('TOURNAMENT_TEST_BOTS_ENABLED')),
        'next_match_id': next_match.id if next_match else None,
    }


def test_bots_enabled():
    """Whether the reserved tournament_bot_* accounts auto-play their turns."""
    return bool(current_app.config.get('TOURNAMENT_TEST_BOTS_ENABLED'))
