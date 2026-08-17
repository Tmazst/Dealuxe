from datetime import datetime, timedelta
import random

from flask import Blueprint, request, jsonify, session, current_app
from flask_socketio import emit, join_room, leave_room
from sqlalchemy import or_

from database import (
    db,
    Tournament,
    TournamentParticipant,
    TournamentBracket,
    TournamentMatch,
    TournamentPrizePool,
    TournamentSchedule,
    MatchRoll,
    Transaction,
    User,
    Player,
    create_tournament_record,
    add_tournament_participant,
    log_transaction,
    TX_ENTRY_FEE,
    TX_PRIZE_AWARD,
    TX_REFUND,
)


tournament_bp = Blueprint('tournament', __name__, url_prefix='/api/tournaments')

# Set by ``init_tournament_events`` during application startup.  Keeping the
# Socket.IO instance here lets the REST and callback-driven flows notify the
# same clients as the WebSocket handlers.
_socketio = None

# Official prize split: 1st = 50%, 2nd = 12.5%, 3rd = 6%  (scope + schema doc)
PRIZE_PERCENTAGES = {1: 0.50, 2: 0.125, 3: 0.06}


def _get_current_user_id():
    return session.get('user_id')


def _tournament_room(tournament_id):
    return f'tournament_{tournament_id}'


def _lock_consensus_info(tournament):
    """Vote status for manual-lock consensus (D3).

    Only non-creator registered participants vote. When every voter has voted,
    the tournament may be locked early at its current player count.
    """
    participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, status='registered'
    ).all()
    voters_needed = [p for p in participants if p.user_id != tournament.creator_id]
    votes_received = sum(1 for p in voters_needed if p.lock_voted)
    return {
        'mode': 'auto' if tournament.is_auto_lock else 'manual',
        'votes_needed': len(voters_needed),
        'votes_received': votes_received,
        'consensus_reached': bool(voters_needed and votes_received >= len(voters_needed)),
    }


def _perform_tournament_lock(tournament):
    """Lock a tournament at its current player count and build its bracket.

    Shared by the creator/admin lock path and the manual-lock consensus path.
    Mirrors the existing lock behaviour (status -> locked, then the bracket
    builder transitions the tournament into 'in_progress' with scheduled matches).
    """
    participant_count = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, status='registered'
    ).count()
    if participant_count < 2:
        return False, 'At least two paid players are required'

    tournament.current_player_count = participant_count
    tournament.status = 'locked'
    tournament.locked_at = datetime.utcnow()
    tournament.locked_player_count = participant_count
    _build_bracket(tournament)
    db.session.commit()

    _announce_tournament_locked(tournament)
    return True, None


def _announce_tournament_locked(tournament, countdown=3):
    """Notify every waiting-room client that the tournament is locked/starting.

    Emits ``tournament_locked`` (lock UI + countdown), ``tournament_starting``
    (auto-redirect to the bracket) and ``tournament_updated`` (public refresh).
    """
    if _socketio is None:
        return
    summary = _serialize_tournament(tournament)
    room = _tournament_room(tournament.id)
    _socketio.emit('tournament_locked', {'tournament': summary}, room=room)
    _socketio.emit('tournament_starting', {'countdown': countdown}, room=room)
    _socketio.emit('tournament_updated', summary, room=room)
    _socketio.emit('tournament_updated', summary, to=None)


def _parse_custom_time(custom_time_str, now):
    """Parse 'HH:MM' (or 'HHMM') into the next occurrence within 24h."""
    if not custom_time_str:
        raise ValueError('Custom start time is required (HH:MM, e.g. 13:30)')
    text = str(custom_time_str).strip().replace(':', '').replace('.', '')
    if not (text.isdigit() and len(text) == 4):
        raise ValueError('Custom start time must be HH:MM, e.g. 13:30')
    hours, minutes = int(text[:2]), int(text[2:])
    if hours > 23 or minutes > 59:
        raise ValueError('Custom start time must be a valid HH:MM time')
    candidate = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate, f'{hours:02d}:{minutes:02d}'


def _resolve_schedule_time(start_option, custom_time_str=None):
    """Validate a start option and return (scheduled_start_at, normalized_option, custom_time_str).

    Raises ValueError on invalid input. `scheduled_start_at` is None for 'seats_filled'.
    """
    if start_option not in START_OPTIONS:
        raise ValueError('Invalid start option')
    now = datetime.utcnow()
    if start_option == 'seats_filled':
        return None, 'seats_filled', None
    if start_option in COUNTDOWN_MINUTES:
        return now + timedelta(minutes=COUNTDOWN_MINUTES[start_option]), start_option, None
    if start_option == 'custom':
        scheduled_at, custom_str = _parse_custom_time(custom_time_str, now)
        if scheduled_at - now >= timedelta(hours=MAX_SCHEDULE_DELAY_HOURS):
            raise ValueError('Scheduled start must be within the next 24 hours')
        return scheduled_at, 'custom', custom_str
    raise ValueError('Invalid start option')


def _serialize_schedule(schedule):
    if schedule is None:
        return {
            'start_option': 'seats_filled',
            'scheduled_start_at': None,
            'custom_time_str': None,
            'fallback_option': 'seats_filled',
        }
    return {
        'start_option': schedule.start_option,
        'scheduled_start_at': schedule.scheduled_start_at.isoformat() if schedule.scheduled_start_at else None,
        'custom_time_str': schedule.custom_time_str,
        'fallback_option': schedule.fallback_option,
    }


def _schedule_message(tournament):
    """Human-readable scheduling message shown when players join a tournament."""
    schedule = tournament.schedule
    if schedule is None or schedule.start_option == 'seats_filled':
        return 'This tournament will start as soon as all seats are filled.'
    if schedule.scheduled_start_at:
        start_local = schedule.scheduled_start_at.strftime('%H:%M')
        return (
            f'This tournament is scheduled to start at {start_local} '
            f'({schedule.start_option.replace("in_", "in ").replace("_", " ")}). '
            'If seats are not filled by then, it will start as soon as they are.'
        )
    return 'This tournament will start as soon as all seats are filled.'


def _serialize_tournament(tournament):
    """Return the stable, UI-facing tournament contract."""
    current_players = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, status='registered'
    ).count()
    return {
        'id': tournament.id,
        'code': tournament.tournament_code,
        'name': tournament.tournament_name,
        'type': tournament.tournament_type,
        'max_players': tournament.max_players,
        'current_players': current_players,
        'entry_fee': tournament.entry_fee,
        'prize_pool': tournament.prize_pool_amount,
        'creator': _get_username(tournament.creator_id),
        'creator_id': tournament.creator_id,
        'status': tournament.status,
        'is_auto_lock': tournament.is_auto_lock,
        'lock': _lock_consensus_info(tournament),
        'schedule': _serialize_schedule(tournament.schedule),
        'schedule_message': _schedule_message(tournament),
        'players_needed': max(tournament.max_players - current_players, 0),
        'created_at': tournament.created_at.isoformat() if tournament.created_at else None,
    }


def _emit_tournament_updated(tournament):
    """Broadcast a public tournament summary when the real-time layer exists."""
    if _socketio is not None:
        _socketio.emit('tournament_updated', _serialize_tournament(tournament),
                       room=_tournament_room(tournament.id))
        _socketio.emit('tournament_updated', _serialize_tournament(tournament), to=None)


def _emit_match_complete(tournament, match):
    if _socketio is not None:
        _socketio.emit('match_complete', _serialize_match(match),
                       room=_tournament_room(tournament.id))


def _can_manage_tournament(tournament, user_id):
    if not user_id:
        return False
    if tournament.creator_id == user_id:
        return True
    user = User.query.get(user_id)
    return bool(user and (user.is_admin or user.is_super_admin))


def _can_view_tournament_members(tournament, user_id):
    if _can_manage_tournament(tournament, user_id):
        return True
    return TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, user_id=user_id, status='registered'
    ).first() is not None


# Official entry fee (scope mandates E10 per player, server-enforced).
ENTRY_FEE = 10.00

# Allowed tournament sizes per type (scope mandates these exact sizes).
MAX_PLAYERS_BY_TYPE = {'standard': 4, 'premium': 8, 'deluxe': 16}

# -----------------------------
# START-TIME SCHEDULING (user feature: schedule the tournament start)
# -----------------------------
START_OPTIONS = ('seats_filled', 'in_5min', 'in_10min', 'in_20min', 'custom')
COUNTDOWN_MINUTES = {'in_5min': 5, 'in_10min': 10, 'in_20min': 20}
MAX_SCHEDULE_DELAY_HOURS = 24
ROLL_COUNTDOWN_SECONDS = 600  # 10 minutes for the no-show roll game


def _is_payment_mock_mode():
    """Return True when the local-debit (sandbox/mock) path should be used."""
    try:
        from flask import current_app
        return bool(current_app.config.get('MOJAPOS_MOCK_MODE', True))
    except Exception:
        return True


def _local_debit_entry(player, amount, tournament_id):
    """Sandbox/mock: debit the wallet directly and record the transaction."""
    balance_before = player.real_balance
    player.real_balance -= amount
    player.total_wagered += amount
    player.deduct_spending(amount)
    log_transaction(
        player_id=player.id,
        transaction_type=TX_ENTRY_FEE,
        amount=amount,
        balance_type='real',
        balance_before=balance_before,
        balance_after=player.real_balance,
        description=f'Tournament entry #{tournament_id}',
        tournament_id=tournament_id,
    )
    return True, None


def _charge_tournament_entry(user_id, amount, tournament_id, tournament_code=None):
    """Charge a user for tournament entry.

    Enforces the E50/24h daily-spend limit (regulatory requirement) before any
    debit. In **mock mode** (default) the wallet is debited directly. When the
    real MojaPOS gateway is enabled, a pending transaction is created and a
    payment is initiated with MojaPOS; the wallet debit + final join happens
    only after the gateway confirms via callback.

    Returns a tuple ``(ok, payload)`` where ``payload`` is either an error
    message (when ``ok`` is False) or a result dict (when ``ok`` is True). The
    result dict includes ``payment_required`` (bool) and, when a real gateway
    call is made, ``payment_url`` / ``transaction_id`` for the client to
    complete the payment.
    """
    player = Player.query.filter_by(user_id=user_id).first()
    if player is None:
        return True, {'payment_required': False}

    if not player.can_spend(amount):
        return False, 'Daily spending limit reached (E50/day)'

    if _is_payment_mock_mode():
        if player.real_balance < amount:
            return False, 'Insufficient balance'
        ok, err = _local_debit_entry(player, amount, tournament_id)
        return ok, {'payment_required': False, 'error': err}

    # ---- Real MojaPOS path: create a pending transaction and initiate ----
    if player.real_balance < amount:
        return False, 'Insufficient balance'

    from services.payment_service import payment_service

    # Reserve the funds (hold) as a pending transaction; full debit happens on
    # callback confirmation.
    transaction = Transaction(
        player_id=player.id,
        transaction_type=TX_ENTRY_FEE,
        amount=amount,
        balance_type='real',
        balance_before=player.real_balance,
        balance_after=player.real_balance,
        tournament_id=tournament_id,
        description=f'Tournament entry #{tournament_id} (pending)',
    )
    db.session.add(transaction)
    db.session.flush()

    phone_number = _get_user_phone(user_id)

    result = payment_service.initiate_tournament_entry_payment(
        transaction_id=transaction.id,
        user_id=user_id,
        amount=amount,
        phone_number=phone_number,
        tournament_code=tournament_code or '',
    )

    if not result.get('success'):
        transaction.status = 'failed'
        db.session.commit()
        return False, result.get('error', 'Payment initiation failed')

    transaction.description = result.get('external_transaction_id') or transaction.description
    db.session.commit()

    return True, {
        'payment_required': True,
        'payment_url': result.get('payment_url'),
        'transaction_id': transaction.id,
        'external_transaction_id': result.get('external_transaction_id'),
        'amount': amount,
    }


def _get_user_phone(user_id):
    """Return a user's phone/mobile-money number if set, else an empty string."""
    user = User.query.get(user_id)
    if user and user.phone:
        return user.phone
    player = Player.query.filter_by(user_id=user_id).first()
    return getattr(player, 'phone', '') or ''


def _ensure_prize_pool(tournament):
    """Recompute the three per-placement prize rows (50% / 12.5% / 6%).

    Should be (re)computed at lock/start so the amounts reflect the final
    prize pool rather than freezing early as players join.
    """
    TournamentPrizePool.query.filter_by(tournament_id=tournament.id).delete()
    rows = []
    for placement, pct in PRIZE_PERCENTAGES.items():
        row = TournamentPrizePool(
            tournament_id=tournament.id,
            placement=placement,
            prize_percentage=round(pct * 100.0, 2),
            prize_amount=round(tournament.prize_pool_amount * pct, 2),
            status='pending',
        )
        db.session.add(row)
        rows.append(row)
    db.session.flush()
    return rows


def _create_match_for_bracket(bracket, tournament, card_count=6):
    """Create a playable match row for a bracket whose two seats are filled."""
    if bracket.player1_id is not None and bracket.player2_id is not None:
        match = TournamentMatch(
            tournament_id=tournament.id,
            bracket_id=bracket.id,
            player1_id=bracket.player1_id,
            player2_id=bracket.player2_id,
            status='scheduled',
            card_count=card_count,
            bet_amount=tournament.entry_fee,
        )
        db.session.add(match)
        db.session.flush()
        bracket.match_id = match.id
        bracket.status = 'scheduled'
        return match
    return None


def _build_bracket(tournament):
    """Create bracket rows and match records for a tournament.

    Generates a single-elimination bracket tree (with byes for non-full locks),
    names the rounds correctly (Semi-Final / Final), shuffles the seeds, and
    adds a third-place playoff fed by the two semi-final losers.
    """
    existing_brackets = TournamentBracket.query.filter_by(tournament_id=tournament.id).all()
    if existing_brackets:
        return existing_brackets

    participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, status='registered'
    ).order_by(TournamentParticipant.registered_at.asc()).all()

    if len(participants) < 2:
        return []

    players = [p.user_id for p in participants]
    random.shuffle(players)

    # Normalise to a power-of-two bracket size, padding with None (byes).
    size = 2
    while size < len(players):
        size *= 2
    seeds = players + [None] * (size - len(players))

    total_rounds = size.bit_length() - 1  # 2 ->1, 4->2, 8->3, 16->4

    # Build round names from the top (Final) backwards.
    round_names = []
    for r in range(total_rounds, 0, -1):
        if r == total_rounds:
            round_names.append('Final')
        elif r == total_rounds - 1:
            round_names.append('Semi-Final')
        elif r == total_rounds - 2 and total_rounds >= 3:
            round_names.append('Quarter-Final')
        else:
            round_names.append(f'Round {total_rounds - r + 1}')
    round_names.reverse()

    bracket_rows = {}  # (round_number, match_number) -> TournamentBracket

    # Round 1 slots from the padded seeds.
    current_slots = [[seeds[i], seeds[i + 1]] for i in range(0, size, 2)]

    for r in range(1, total_rounds + 1):
        num_matches = len(current_slots)
        for m_idx in range(num_matches):
            p1, p2 = current_slots[m_idx]
            bracket = TournamentBracket(
                tournament_id=tournament.id,
                round_number=r,
                round_name=round_names[r - 1],
                match_number=m_idx + 1,
                player1_id=p1,
                player2_id=p2,
                status='pending',
            )
            db.session.add(bracket)
            db.session.flush()
            bracket_rows[(r, m_idx + 1)] = bracket

            if p1 is not None and p2 is not None:
                _create_match_for_bracket(bracket, tournament)
            elif p1 is not None or p2 is not None:
                # Bye: the lone player auto-advances.
                winner = p1 if p1 is not None else p2
                bracket.winner_id = winner
                bracket.status = 'completed'
                bracket.completed_at = datetime.utcnow()

        # Build the next round slots from this round's known winners (byes).
        if r < total_rounds:
            next_slots = [[None, None] for _ in range(num_matches // 2)]
            for g in range(0, num_matches, 2):
                b1 = bracket_rows.get((r, g + 1))
                b2 = bracket_rows.get((r, g + 2))
                w1 = b1.winner_id if b1 else None
                w2 = b2.winner_id if b2 else None
                next_slots[g // 2][0] = w1
                next_slots[g // 2][1] = w2
            current_slots = next_slots

    db.session.commit()

    # Fill playable matches for rounds > 1 whose two players are already known
    # (auto-advanced byes), e.g. a direct into the Final.
    for key, bracket in list(bracket_rows.items()):
        if key[0] >= 2 and bracket.match_id is None \
           and bracket.player1_id is not None and bracket.player2_id is not None \
           and bracket.status != 'completed':
            _create_match_for_bracket(bracket, tournament)

    # A third-place game requires two real semi-final losers.  A tournament
    # locked with only three players has a bye, so creating this row would
    # leave it permanently unplayable and prevent finalization.
    if total_rounds >= 2 and len(players) >= 4:
        third_bracket = TournamentBracket(
            tournament_id=tournament.id,
            round_number=total_rounds + 1,
            round_name='Third-Place',
            match_number=1,
            player1_id=None,
            player2_id=None,
            status='pending',
        )
        db.session.add(third_bracket)
        db.session.flush()

    db.session.commit()

    # Authoritative prize recalculation at lock/start.
    _ensure_prize_pool(tournament)

    tournament.status = 'in_progress'
    tournament.started_at = datetime.utcnow()
    db.session.commit()

    return TournamentBracket.query.filter_by(tournament_id=tournament.id).all()


def _get_username(user_id):
    if not user_id:
        return None
    user = User.query.get(user_id)
    return user.username if user else None


def _serialize_participant(participant):
    return {
        'user_id': participant.user_id,
        'username': _get_username(participant.user_id),
        'is_creator': participant.user_id == participant.tournament.creator_id,
        'status': participant.status,
        'payment_status': participant.payment_status,
        'lock_voted': bool(participant.lock_voted),
        'paid_amount': participant.paid_amount,
        'registered_at': participant.registered_at.isoformat() if participant.registered_at else None,
    }


def _withdraw_participant(tournament, participant):
    """Withdraw a registered player before lock and refund a mock-wallet entry."""
    if tournament.status != 'open':
        return False, 'Tournament has already been locked'
    if participant.status != 'registered':
        return False, 'You are not an active tournament participant'
    if participant.payment_status != 'completed':
        participant.status = 'withdrawn'
        participant.withdrew_at = datetime.utcnow()
        return True, None
    if not _is_payment_mock_mode():
        return False, 'Completed mobile-money payments cannot be refunded from the waiting room'

    player = Player.query.filter_by(user_id=participant.user_id).first()
    amount = participant.paid_amount or tournament.entry_fee
    if player is not None and amount > 0:
        balance_before = player.real_balance
        player.real_balance += amount
        player.total_wagered = max(0.0, player.total_wagered - amount)
        player.daily_spending_amount = max(0.0, player.daily_spending_amount - amount)
        log_transaction(
            player_id=player.id,
            transaction_type=TX_REFUND,
            amount=amount,
            balance_type='real',
            balance_before=balance_before,
            balance_after=player.real_balance,
            description=f'Tournament entry refund #{tournament.id}',
            tournament_id=tournament.id,
        )

    participant.status = 'withdrawn'
    participant.payment_status = 'refunded'
    participant.withdrew_at = datetime.utcnow()
    tournament.current_player_count = max(0, tournament.current_player_count - 1)
    tournament.prize_pool_amount = max(0.0, tournament.prize_pool_amount - amount)
    _ensure_prize_pool(tournament)
    return True, None


def _serialize_bracket(bracket):
    return {
        'id': bracket.id,
        'round_number': bracket.round_number,
        'round_name': bracket.round_name,
        'match_number': bracket.match_number,
        'player1_id': bracket.player1_id,
        'player2_id': bracket.player2_id,
        'player1_name': _get_username(bracket.player1_id),
        'player2_name': _get_username(bracket.player2_id),
        'status': bracket.status,
        'winner_id': bracket.winner_id,
        'winner_name': _get_username(bracket.winner_id),
        'match_id': bracket.match_id,
        'started_at': bracket.started_at.isoformat() if bracket.started_at else None,
        'completed_at': bracket.completed_at.isoformat() if bracket.completed_at else None,
    }


def _serialize_match(match):
    room_code = None
    player1_connected = False
    player2_connected = False
    if match.game_room_id:
        from database import GameRoom
        room = GameRoom.query.get(match.game_room_id)
        if room:
            room_code = room.room_code
            player1_connected = bool(room.player1_connected)
            player2_connected = bool(room.player2_connected)

    roll = MatchRoll.query.filter_by(match_id=match.id, status='rolling').first()
    return {
        'id': match.id,
        'bracket_id': match.bracket_id,
        'game_room_id': match.game_room_id,
        'room_code': room_code,
        'player1_id': match.player1_id,
        'player2_id': match.player2_id,
        'player1_name': _get_username(match.player1_id),
        'player2_name': _get_username(match.player2_id),
        'status': match.status,
        'winner_id': match.winner_id,
        'loser_id': match.loser_id,
        'winner_name': _get_username(match.winner_id),
        'bet_amount': match.bet_amount,
        'card_count': match.card_count,
        'scheduled_for': match.scheduled_for.isoformat() if match.scheduled_for else None,
        'started_at': match.started_at.isoformat() if match.started_at else None,
        'completed_at': match.completed_at.isoformat() if match.completed_at else None,
        'win_type': match.win_type,
        'player1_connected': player1_connected,
        'player2_connected': player2_connected,
        'roll': {
            'status': roll.status if roll else None,
            'requested_by': roll.requested_by if roll else None,
            'deadline': roll.deadline.isoformat() if roll and roll.deadline else None,
        },
    }


def _build_rounds(tournament):
    brackets = TournamentBracket.query.filter_by(tournament_id=tournament.id).order_by(
        TournamentBracket.round_number, TournamentBracket.match_number
    ).all()
    rounds = {}
    for bracket in brackets:
        entry = _serialize_bracket(bracket)
        rounds.setdefault(bracket.round_number, {
            'round_number': bracket.round_number,
            'round_name': bracket.round_name,
            'matches': []
        })['matches'].append(entry)
    return [rounds[key] for key in sorted(rounds.keys())]


def _tournament_stats(tournament, matches, participants):
    completed = sum(1 for m in matches if m.status == 'completed')
    scheduled = sum(1 for m in matches if m.status in {'scheduled', 'pending'})
    return {
        'participant_count': len(participants),
        'total_matches': len(matches),
        'completed_matches': completed,
        'scheduled_matches': scheduled,
        'current_status': tournament.status,
        'prize_pool_amount': tournament.prize_pool_amount,
    }


def _finalize_tournament(tournament):
    """Award prizes to 1st/2nd/3rd, credit wallets, and finalize the tournament."""
    placements = {
        1: tournament.winner_id,
        2: tournament.runner_up_id,
        3: tournament.third_place_id,
    }

    tournament.status = 'completed'
    tournament.completed_at = datetime.utcnow()

    for placement, user_id in placements.items():
        if not user_id:
            continue

        row = TournamentPrizePool.query.filter_by(
            tournament_id=tournament.id, placement=placement
        ).first()
        amount = row.prize_amount if row else 0.0

        participant = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, user_id=user_id
        ).first()
        if participant:
            participant.final_placement = placement
            participant.prize_awarded = amount
            participant.status = 'active'

        if row:
            row.user_id = user_id
            row.status = 'awarded'
            row.award_date = datetime.utcnow()

        # Credit the player's real wallet.
        player = Player.query.filter_by(user_id=user_id).first()
        if player is not None and amount > 0:
            balance_before = player.real_balance
            player.real_balance += amount
            player.total_winnings += amount
            log_transaction(
                player_id=player.id,
                transaction_type=TX_PRIZE_AWARD,
                amount=amount,
                balance_type='real',
                balance_before=balance_before,
                balance_after=player.real_balance,
                description=f'Tournament #{tournament.id} prize (placement {placement})',
                tournament_id=tournament.id,
            )


def _maybe_finalize(tournament):
    """Finalize once all podium positions are known."""
    has_third_place = TournamentBracket.query.filter_by(
        tournament_id=tournament.id, round_name='Third-Place'
    ).first() is not None

    podium_ready = tournament.winner_id and tournament.runner_up_id
    if has_third_place:
        podium_ready = podium_ready and tournament.third_place_id

    if podium_ready:
        _finalize_tournament(tournament)


def init_tournament_events(socketio, app=None):
    """Register the authenticated real-time tournament UI events."""
    global _socketio
    _socketio = socketio

    def get_tournament_from_payload(data):
        code = (data or {}).get('tournament_code')
        if not code or not isinstance(code, str):
            emit('tournament_error', {'message': 'Tournament code is required'})
            return None
        tournament = Tournament.query.filter_by(tournament_code=code.strip()).first()
        if tournament is None:
            emit('tournament_error', {'message': 'Tournament not found'})
        return tournament

    @socketio.on('get_tournaments')
    def handle_get_tournaments(data=None):
        data = data or {}
        filter_name = data.get('filter', 'all')
        valid_filters = {'all', 'open', 'locked', 'in_progress', 'completed'}
        if filter_name not in valid_filters:
            emit('tournament_error', {'message': 'Invalid tournament filter'})
            return
        try:
            limit = max(1, min(int(data.get('limit', 50)), 100))
        except (TypeError, ValueError):
            limit = 50

        query = Tournament.query.order_by(Tournament.created_at.desc())
        if filter_name != 'all':
            query = query.filter_by(status=filter_name)
        tournaments = query.limit(limit).all()
        emit('tournaments_list', {
            'tournaments': [_serialize_tournament(t) for t in tournaments],
            'count': len(tournaments),
        })

    @socketio.on('join_tournament_room')
    def handle_join_tournament_room(data=None):
        user_id = _get_current_user_id()
        if not user_id:
            emit('tournament_error', {'message': 'Authentication required'})
            return
        tournament = get_tournament_from_payload(data)
        if tournament is None:
            return
        if not _can_view_tournament_members(tournament, user_id):
            emit('tournament_error', {'message': 'Join the tournament before entering its waiting room'})
            return

        join_room(_tournament_room(tournament.id))
        summary = _serialize_tournament(tournament)
        emit('joined_tournament', {
            'tournament': summary,
            'is_creator': _can_manage_tournament(tournament, user_id),
        })
        emit('tournament_updated', summary)
        emit('tournament_participants', {
            'participants': [_serialize_participant(p) for p in TournamentParticipant.query.filter_by(
                tournament_id=tournament.id, status='registered'
            ).order_by(TournamentParticipant.registered_at.asc()).all()]
        })

    @socketio.on('get_tournament_participants')
    def handle_get_tournament_participants(data=None):
        user_id = _get_current_user_id()
        if not user_id:
            emit('tournament_error', {'message': 'Authentication required'})
            return
        tournament = get_tournament_from_payload(data)
        if tournament is None:
            return
        if not _can_view_tournament_members(tournament, user_id):
            emit('tournament_error', {'message': 'You cannot view these participants'})
            return
        participants = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, status='registered'
        ).order_by(TournamentParticipant.registered_at.asc()).all()
        emit('tournament_participants', {
            'participants': [_serialize_participant(p) for p in participants]
        })

    @socketio.on('request_tournament_lock')
    def handle_request_tournament_lock(data=None):
        user_id = _get_current_user_id()
        tournament = get_tournament_from_payload(data)
        if tournament is None:
            return
        if not _can_manage_tournament(tournament, user_id):
            emit('tournament_error', {'message': 'Only the creator can lock this tournament'})
            return
        if tournament.status != 'open':
            emit('tournament_error', {'message': 'Tournament is already locked or completed'})
            return

        ok, error = _perform_tournament_lock(tournament)
        if not ok:
            emit('tournament_error', {'message': error})

    @socketio.on('vote_tournament_lock')
    def handle_vote_tournament_lock(data=None):
        """Manual-lock consensus (D3): every registered non-creator player votes.

        When all voters have voted the tournament locks early at its current
        player count. Broadcasts `lock_votes_updated` with the vote totals.
        """
        user_id = _get_current_user_id()
        if not user_id:
            emit('tournament_error', {'message': 'Authentication required'})
            return
        tournament = get_tournament_from_payload(data)
        if tournament is None:
            return
        participant = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, user_id=user_id, status='registered'
        ).first()
        if participant is None:
            emit('tournament_error', {'message': 'You are not an active participant'})
            return
        if tournament.status != 'open':
            emit('tournament_error', {'message': 'Tournament is already locked or completed'})
            return
        if tournament.is_auto_lock:
            emit('tournament_error', {'message': 'This tournament is set to auto lock itself when players full'})
            return
        if _can_manage_tournament(tournament, user_id):
            emit('tournament_error', {'message': 'The creator or admin locks directly'})
            return

        if not participant.lock_voted:
            participant.lock_voted = True
            db.session.commit()

        lock_info = _lock_consensus_info(tournament)
        tournament_locked = False
        if lock_info['consensus_reached']:
            ok, error = _perform_tournament_lock(tournament)
            tournament_locked = ok

        socketio.emit('lock_votes_updated', {
            **lock_info,
            'tournament_locked': tournament_locked,
        }, room=_tournament_room(tournament.id))

    @socketio.on('leave_tournament')
    def handle_leave_tournament(data=None):
        user_id = _get_current_user_id()
        if not user_id:
            emit('tournament_error', {'message': 'Authentication required'})
            return
        tournament = get_tournament_from_payload(data)
        if tournament is None:
            return

        if tournament.status in ('in_progress', 'completed', 'cancelled'):
            emit('tournament_error', {'message': 'Tournament is already in progress or started'})
            return

        participant = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, user_id=user_id
        ).first()
        if participant is None:
            emit('tournament_error', {'message': 'You are not a tournament participant'})
            return

        ok, error = _withdraw_participant(tournament, participant)
        if not ok:
            emit('tournament_error', {'message': error})
            return
        db.session.commit()
        leave_room(_tournament_room(tournament.id))
        socketio.emit('participant_left', {
            'user_id': user_id,
            'username': _get_username(user_id),
            'current_players': _serialize_tournament(tournament)['current_players'],
        }, room=_tournament_room(tournament.id))
        _emit_tournament_updated(tournament)

    @socketio.on('start_tournament_match')
    def handle_start_tournament_match(data=None):
        data = data or {}
        user_id = _get_current_user_id()
        if not user_id:
            emit('tournament_error', {'message': 'Authentication required'})
            return
        tournament_id = data.get('tournament_id')
        match_id = data.get('match_id')
        if not tournament_id or not match_id:
            emit('tournament_error', {'message': 'tournament_id and match_id are required'})
            return
        match, response, code = start_tournament_match_helper(tournament_id, match_id, user_id=user_id)
        if code != 200:
            emit('tournament_error', response)
        else:
            emit('tournament_match_started_response', response)

    @socketio.on('roll_match')
    def handle_roll_match(data=None):
        """Start the 10-minute no-show roll for a tournament match."""
        user_id = _get_current_user_id()
        if not user_id:
            emit('tournament_error', {'message': 'Authentication required'})
            return
        tournament = get_tournament_from_payload(data)
        if tournament is None:
            return
        match_id = (data or {}).get('match_id')
        match = TournamentMatch.query.filter_by(id=match_id, tournament_id=tournament.id).first()
        if match is None:
            emit('tournament_error', {'message': 'Match not found'})
            return
        if match.status in ('completed', 'cancelled'):
            emit('tournament_error', {'message': 'Match is already finished'})
            return
        if user_id not in {match.player1_id, match.player2_id}:
            emit('tournament_error', {'message': 'Only match participants can roll the game'})
            return
        roll, payload = _start_roll(match, user_id)
        emit('match_roll_started_response', payload or {
            'match_id': match.id,
            'deadline': roll.deadline.isoformat(),
            'message': 'The roll is already active.',
        })

    @socketio.on('join_bracket_room')
    def handle_join_bracket_room(data=None):
        """Allow bracket viewers (players + spectators) to receive live updates."""
        code = (data or {}).get('tournament_code')
        if not code or not isinstance(code, str):
            return
        tournament = Tournament.query.filter_by(tournament_code=code.strip()).first()
        if tournament is None:
            return
        join_room(_tournament_room(tournament.id))

    return socketio


@tournament_bp.route('', methods=['GET'])
def list_tournaments():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return jsonify({'tournaments': [_serialize_tournament(t) for t in tournaments]})


@tournament_bp.route('/me/active', methods=['GET'])
def my_active_tournaments():
    """Return tournaments the current user is still part of (open/locked/in_progress).

    Used by the tournament arena page to hide the "Create tournament" CTA while
    the player already has a tournament in progress.
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    active = Tournament.query.filter(
        Tournament.status.in_(['open', 'locked', 'in_progress'])
    ).order_by(Tournament.created_at.desc()).all()

    mine = []
    for tournament in active:
        is_participant = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, user_id=user_id, status='registered'
        ).first() is not None
        if tournament.creator_id == user_id or is_participant:
            mine.append(_serialize_tournament(tournament))

    return jsonify({'tournaments': mine})


@tournament_bp.route('/me/next-match', methods=['GET'])
def my_next_match():
    """Return the current user's next scheduled or live tournament match.

    Powers the "Next Match" CTA on the tournament arena page. Prefers a live
    match (in_progress) over scheduled fixtures, and only considers matches in
    tournaments that are still running.
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    candidates = TournamentMatch.query.filter(
        or_(
            TournamentMatch.player1_id == user_id,
            TournamentMatch.player2_id == user_id,
        ),
        TournamentMatch.status.in_(['scheduled', 'pending', 'in_progress']),
    ).all()

    # in_progress first, then by scheduled time / creation order
    candidates.sort(key=lambda m: (
        0 if m.status == 'in_progress' else 1,
        m.scheduled_for if m.scheduled_for else datetime.min,
        m.id,
    ))

    for match in candidates:
        tournament = Tournament.query.get(match.tournament_id)
        if tournament is None or tournament.status not in ('open', 'locked', 'in_progress'):
            continue

        room_code = None
        if match.game_room_id:
            from database import GameRoom
            room = GameRoom.query.get(match.game_room_id)
            if room is not None:
                room_code = room.room_code

        bracket = TournamentBracket.query.get(match.bracket_id) if match.bracket_id else None
        opponent_id = match.player2_id if match.player1_id == user_id else match.player1_id

        return jsonify({
            'has_match': True,
            'match': {
                'id': match.id,
                'tournament_id': tournament.id,
                'tournament_code': tournament.tournament_code,
                'tournament_name': tournament.tournament_name,
                'round_name': bracket.round_name if bracket else None,
                'status': match.status,
                'user_id': user_id,
                'self_name': _get_username(user_id),
                'opponent_id': opponent_id,
                'opponent_name': _get_username(opponent_id),
                'player1_name': _get_username(match.player1_id),
                'player2_name': _get_username(match.player2_id),
                'room_code': room_code,
                'started_at': match.started_at.isoformat() if match.started_at else None,
                'scheduled_for': match.scheduled_for.isoformat() if match.scheduled_for else None,
                'tournament_url': f'/tournaments/{tournament.id}',
                'bracket_url': f'/tournaments/{tournament.id}/bracket',
                'game_url': f'/game/{room_code}' if room_code else None,
            },
        }), 200

    return jsonify({'has_match': False})


@tournament_bp.route('/create', methods=['POST'])
def create_tournament():
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    tournament_type = data.get('tournament_type', 'standard')
    tournament_name = data.get('tournament_name') or f"{tournament_type.title()} Tournament"

    if tournament_type not in {'standard', 'premium', 'deluxe'}:
        return jsonify({'error': 'Invalid tournament type'}), 400

    # Validate the start-time schedule BEFORE creating anything.
    try:
        scheduled_start_at, normalized_option, normalized_custom_time = _resolve_schedule_time(
            data.get('start_option', 'seats_filled'), data.get('custom_time_str')
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # Server-enforced business rules (C3): E10 entry fee + fixed size per type.
    entry_fee = ENTRY_FEE
    max_players = MAX_PLAYERS_BY_TYPE.get(tournament_type, 4)

    tournament = create_tournament_record(
        creator_id=user_id,
        tournament_type=tournament_type,
        tournament_name=tournament_name,
        entry_fee=entry_fee,
        max_players=max_players,
        is_auto_lock=data.get('is_auto_lock', False),
        locked_player_count=data.get('locked_player_count'),
    )
    schedule = TournamentSchedule(
        tournament_id=tournament.id,
        start_option=normalized_option,
        scheduled_start_at=scheduled_start_at,
        custom_time_str=normalized_custom_time,
        fallback_option='seats_filled',
    )
    db.session.add(schedule)
    participant = add_tournament_participant(
        tournament.id, user_id, payment_status='pending', payment_method='wallet'
    )
    participant.status = 'pending'

    paid, charge_result = _charge_tournament_entry(
        user_id, entry_fee, tournament.id, tournament.tournament_code
    )
    if not paid:
        db.session.rollback()
        error_msg = charge_result if isinstance(charge_result, str) else (charge_result or {}).get('error')
        return jsonify({'error': error_msg}), 402

    if charge_result.get('payment_required'):
        participant.transaction_id = str(charge_result.get('transaction_id') or '')
        tournament.current_player_count = 0
        tournament.prize_pool_amount = 0.0
        db.session.commit()
        return jsonify({
            'tournament': _serialize_tournament(tournament),
            'payment': charge_result,
            'message': 'Complete payment to create the tournament',
        }), 202

    participant.payment_status = 'completed'
    participant.status = 'registered'
    participant.payment_completed_at = datetime.utcnow()
    participant.paid_amount = entry_fee
    tournament.current_player_count = 1
    tournament.prize_pool_amount = entry_fee
    _ensure_prize_pool(tournament)
    db.session.commit()
    _emit_tournament_updated(tournament)

    return jsonify({'tournament': _serialize_tournament(tournament), 'message': 'Tournament created'})


@tournament_bp.route('/<int:tournament_id>/join', methods=['POST'])
def join_tournament(tournament_id):
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    tournament = Tournament.query.get_or_404(tournament_id)
    if tournament.status != 'open':
        return jsonify({'error': 'Tournament is not open'}), 400

    already_registered = TournamentParticipant.query.filter_by(tournament_id=tournament.id, user_id=user_id).first()
    if already_registered:
        return jsonify({'error': 'Already registered'}), 400

    if tournament.current_player_count >= tournament.max_players:
        return jsonify({'error': 'Tournament is full'}), 400

    participant = add_tournament_participant(
        tournament.id, user_id, payment_status='pending', payment_method='wallet'
    )
    participant.status = 'pending'
    paid, charge_result = _charge_tournament_entry(
        user_id, tournament.entry_fee, tournament.id, tournament.tournament_code
    )
    if not paid:
        db.session.rollback()
        return jsonify({'error': charge_result}), 402
    if charge_result.get('payment_required'):
        participant.transaction_id = str(charge_result.get('transaction_id') or '')
        db.session.commit()
        return jsonify({
            'message': 'Complete payment to join the tournament',
            'participant': {'id': participant.id, 'user_id': user_id},
            'payment': charge_result,
        }), 202

    participant.payment_status = 'completed'
    participant.status = 'registered'
    participant.payment_completed_at = datetime.utcnow()
    participant.paid_amount = tournament.entry_fee
    tournament.current_player_count += 1
    tournament.prize_pool_amount += tournament.entry_fee
    _ensure_prize_pool(tournament)

    # Notify waiting rooms so their participant list refreshes in real time.
    if _socketio is not None:
        _socketio.emit('participant_joined', {
            'user_id': user_id,
            'username': _get_username(user_id),
            'current_players': tournament.current_player_count,
        }, room=_tournament_room(tournament.id))

    if tournament.current_player_count >= tournament.max_players and tournament.is_auto_lock:
        # Seats are full on an auto-lock bracket: lock it, build the bracket and
        # announce (tournament_locked + tournament_starting) so every waiting
        # room auto-redirects to the bracket page.
        _perform_tournament_lock(tournament)
    else:
        db.session.commit()
        _emit_tournament_updated(tournament)

    return jsonify({
        'message': 'Joined tournament',
        'tournament_message': _schedule_message(tournament),
        'schedule': _serialize_schedule(tournament.schedule),
        'participant': {'id': participant.id, 'user_id': user_id},
    })


@tournament_bp.route('/<int:tournament_id>/lock', methods=['POST'])
def lock_tournament(tournament_id):
    user_id = _get_current_user_id()
    tournament = Tournament.query.get_or_404(tournament_id)

    # Restrict manual locking to the creator (or an admin).
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    if not _can_manage_tournament(tournament, user_id):
        return jsonify({'error': 'Only the creator can lock this tournament'}), 403

    if tournament.status != 'open':
        return jsonify({'error': 'Tournament already locked or completed'}), 400

    ok, error = _perform_tournament_lock(tournament)
    if not ok:
        return jsonify({'error': error}), 400

    return jsonify({'message': 'Tournament locked', 'tournament': _serialize_tournament(tournament)})


@tournament_bp.route('/<int:tournament_id>/vote-lock', methods=['POST'])
def vote_tournament_lock_rest(tournament_id):
    """Manual-lock consensus (D3): cast the caller's vote to lock the tournament."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    tournament = Tournament.query.get_or_404(tournament_id)
    participant = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, user_id=user_id, status='registered'
    ).first()
    if participant is None:
        return jsonify({'error': 'You are not an active participant'}), 400
    if tournament.status != 'open':
        return jsonify({'error': 'Tournament is already locked or completed'}), 400
    if tournament.is_auto_lock:
        return jsonify({'error': 'This tournament uses auto-lock when full'}), 400
    if _can_manage_tournament(tournament, user_id):
        return jsonify({'error': 'The creator or admin locks directly'}), 400

    if not participant.lock_voted:
        participant.lock_voted = True
        db.session.commit()

    lock_info = _lock_consensus_info(tournament)
    tournament_locked = False
    if lock_info['consensus_reached']:
        ok, error = _perform_tournament_lock(tournament)
        tournament_locked = ok

    return jsonify({**lock_info, 'tournament_locked': tournament_locked})


@tournament_bp.route('/<int:tournament_id>/generate-bracket', methods=['POST'])
def generate_bracket(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    if tournament.status not in {'locked', 'open'}:
        return jsonify({'error': 'Tournament must be open or locked'}), 400

    brackets = _build_bracket(tournament)
    return jsonify({'message': 'Bracket generated', 'bracket_count': len(brackets)})


@tournament_bp.route('/<int:tournament_id>/overview', methods=['GET'])
def tournament_overview(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    participants = TournamentParticipant.query.filter_by(tournament_id=tournament.id).all()
    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).order_by(TournamentMatch.id.asc()).all()

    next_matches = [m for m in matches if m.status in {'scheduled', 'pending'}]
    recent_results = [m for m in matches if m.status == 'completed']

    return jsonify({
        'tournament': tournament.to_dict(),
        'participants': [_serialize_participant(p) for p in participants],
        'rounds': _build_rounds(tournament),
        'matches': [_serialize_match(m) for m in matches],
        'next_matches': [_serialize_match(m) for m in next_matches[:5]],
        'recent_results': [_serialize_match(m) for m in recent_results[-5:]][::-1],
        'stats': _tournament_stats(tournament, matches, participants),
    })


def record_tournament_match_result(match_id, winner_id, loser_id, win_type='normal', started_at=None, duration_seconds=None):
    """
    Server-authoritative recording of a tournament match result.
    Updates TournamentMatch, TournamentBracket, advances bracket seats, routes semi-final losers to 3rd place,
    triggers tournament finalization checks, and broadcasts real-time socket events.
    """
    match = TournamentMatch.query.get(match_id)
    if not match:
        return None, "Match not found"

    tournament = Tournament.query.get(match.tournament_id)
    if not tournament:
        return None, "Tournament not found"

    if match.status == 'completed':
        return match, "Match already completed"

    now = datetime.utcnow()
    if match.started_at is None:
        match.started_at = started_at or now

    match.status = 'completed'
    match.winner_id = winner_id
    match.loser_id = loser_id
    match.win_type = win_type or 'normal'
    match.completed_at = now
    if duration_seconds is not None:
        match.duration_seconds = duration_seconds
    elif match.started_at:
        match.duration_seconds = int((now - match.started_at).total_seconds())

    bracket = TournamentBracket.query.get(match.bracket_id)
    if bracket is not None:
        bracket.status = 'completed'
        bracket.winner_id = winner_id
        bracket.completed_at = now

    winner_participant = TournamentParticipant.query.filter_by(tournament_id=tournament.id, user_id=winner_id).first()
    loser_participant = TournamentParticipant.query.filter_by(tournament_id=tournament.id, user_id=loser_id).first()
    if winner_participant is not None:
        winner_participant.status = 'active'
    if loser_participant is not None:
        loser_participant.status = 'eliminated'

    # ---- Finals completed ----
    if bracket is not None and bracket.round_name == 'Final':
        tournament.winner_id = winner_id
        tournament.runner_up_id = loser_id

    # ---- Third-place completed ----
    elif bracket is not None and bracket.round_name == 'Third-Place':
        tournament.third_place_id = winner_id

    # ---- Semi-final: route loser into the third-place bracket ----
    elif bracket is not None and bracket.round_name == 'Semi-Final':
        third_bracket = TournamentBracket.query.filter_by(
            tournament_id=tournament.id, round_name='Third-Place'
        ).first()
        if third_bracket is not None:
            if third_bracket.player1_id is None:
                third_bracket.player1_id = loser_id
            elif third_bracket.player2_id is None:
                third_bracket.player2_id = loser_id

            if third_bracket.player1_id is not None and third_bracket.player2_id is not None:
                third_match = TournamentMatch.query.filter_by(bracket_id=third_bracket.id).first()
                if third_match is None:
                    third_match = _create_match_for_bracket(third_bracket, tournament)
                tournament.third_place_match_id = third_bracket.match_id
                if third_match is not None:
                    third_match.status = 'scheduled'

    # ---- Route winner into the next round (non-final, non-third-place) ----
    if bracket is not None and bracket.round_name not in ('Final', 'Third-Place'):
        next_round = bracket.round_number + 1
        next_match_number = (bracket.match_number + 1) // 2
        next_bracket = TournamentBracket.query.filter_by(
            tournament_id=tournament.id,
            round_number=next_round,
            match_number=next_match_number,
        ).first()

        if next_bracket is not None and next_bracket.status != 'completed':
            if next_bracket.player1_id is None:
                next_bracket.player1_id = winner_id
            elif next_bracket.player2_id is None:
                next_bracket.player2_id = winner_id

            if next_bracket.player1_id is not None and next_bracket.player2_id is not None:
                next_match = TournamentMatch.query.filter_by(bracket_id=next_bracket.id).first()
                if next_match is None:
                    next_match = _create_match_for_bracket(next_bracket, tournament)
                if next_match is not None:
                    next_match.status = 'scheduled'

    _maybe_finalize(tournament)

    db.session.commit()
    _emit_match_complete(tournament, match)
    _emit_tournament_updated(tournament)

    return match, None


# -----------------------------
# ROLL GAME (no-show resolution)
# -----------------------------

def _start_roll(match, user_id):
    """Start (or resume) the 10-minute no-show roll for a tournament match.

    Notifies the tournament room and the opponent's user room. Returns
    (roll, payload) where payload is the broadcast payload (or None when an
    active roll already exists).
    """
    existing = MatchRoll.query.filter_by(match_id=match.id, status='rolling').first()
    if existing:
        return existing, None

    roll = MatchRoll(
        match_id=match.id,
        requested_by=user_id,
        deadline=datetime.utcnow() + timedelta(seconds=ROLL_COUNTDOWN_SECONDS),
        status='rolling',
    )
    db.session.add(roll)
    db.session.commit()

    opponent_id = match.player2_id if match.player1_id == user_id else match.player1_id
    tournament = Tournament.query.get(match.tournament_id)
    payload = {
        'match_id': match.id,
        'tournament_id': match.tournament_id,
        'requested_by': user_id,
        'requested_by_name': _get_username(user_id),
        'opponent_id': opponent_id,
        'deadline': roll.deadline.isoformat(),
        'message': f'{_get_username(user_id)} is rolling the game. Join within 10 minutes or the match will be awarded by no-show.',
    }
    if _socketio is not None:
        if tournament is not None:
            _socketio.emit('match_roll_started', payload, room=_tournament_room(tournament.id))
        if opponent_id:
            _socketio.emit('match_roll_started', payload, room=f'user_{opponent_id}')
    return roll, payload


def _resolve_roll(roll):
    """Resolve an expired roll: the waiting player wins by no-show."""
    match = TournamentMatch.query.get(roll.match_id)
    if match is None or match.status in ('completed', 'cancelled'):
        roll.status = 'cancelled'
        db.session.commit()
        return None

    winner_id = roll.requested_by
    loser_id = match.player2_id if match.player1_id == winner_id else match.player1_id
    if loser_id is None:
        roll.status = 'cancelled'
        db.session.commit()
        return None

    record_tournament_match_result(
        match_id=match.id,
        winner_id=winner_id,
        loser_id=loser_id,
        win_type='no_show',
        started_at=match.started_at,
        duration_seconds=ROLL_COUNTDOWN_SECONDS,
    )
    roll.status = 'resolved'
    roll.winner_id = winner_id
    roll.resolved_at = datetime.utcnow()
    db.session.commit()

    tournament = Tournament.query.get(match.tournament_id)
    resolved_payload = {
        'match_id': match.id,
        'tournament_id': match.tournament_id,
        'winner_id': winner_id,
        'winner_name': _get_username(winner_id),
        'message': f'No-show resolved — {_get_username(winner_id)} wins the match by roll.',
    }
    if _socketio is not None:
        if tournament is not None:
            room = _tournament_room(tournament.id)
            _socketio.emit('match_roll_resolved', resolved_payload, room=room)
        _socketio.emit('match_roll_resolved', resolved_payload, room=f'user_{winner_id}')
        _socketio.emit('match_roll_resolved', resolved_payload, room=f'user_{loser_id}')
    return resolved_payload


def process_scheduled_events():
    """Background worker: fire due tournament starts and resolve expired rolls.

    Called periodically from the app-level scheduler thread (see app.py).
    """
    now = datetime.utcnow()

    # 1) Due scheduled tournament starts (with seats-filled fallback)
    schedules = TournamentSchedule.query.filter(
        TournamentSchedule.scheduled_start_at.isnot(None),
        TournamentSchedule.scheduled_start_at <= now,
    ).all()
    for schedule in schedules:
        tournament = Tournament.query.get(schedule.tournament_id)
        if tournament is None or tournament.status != 'open':
            continue
        registered = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, status='registered'
        ).count()
        if registered >= tournament.max_players:
            _perform_tournament_lock(tournament)
        else:
            # Fallback to option 1: start as soon as seats are filled.
            schedule.start_option = 'seats_filled'
            schedule.scheduled_start_at = None
            db.session.commit()
            if _socketio is not None:
                _socketio.emit('tournament_schedule_fallback', {
                    'message': 'Scheduled start time passed — this tournament will start as soon as all seats are filled.',
                }, room=_tournament_room(tournament.id))
            _emit_tournament_updated(tournament)

    # 2) Expired no-show roll deadlines
    rolls = MatchRoll.query.filter(
        MatchRoll.status == 'rolling',
        MatchRoll.deadline <= now,
    ).all()
    for roll in rolls:
        _resolve_roll(roll)


def start_tournament_match_helper(tournament_id, match_id, user_id=None):
    """
    Start a scheduled tournament match by creating or linking a real GameRoom,
    initializing the GameEngine, and setting room status.
    """
    from database import GameRoom
    from controllers.multiplayer_controller import generate_room_code

    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        return None, {'error': 'Tournament not found'}, 404

    match = TournamentMatch.query.filter_by(id=match_id, tournament_id=tournament.id).first()
    if not match:
        return None, {'error': 'Match not found'}, 404

    if user_id:
        is_participant = user_id in {match.player1_id, match.player2_id}
        is_creator_or_admin = _can_manage_tournament(tournament, user_id)
        if not (is_participant or is_creator_or_admin):
            return None, {'error': 'Not authorized to start this match'}, 403

    if match.status == 'completed':
        return None, {'error': 'Match is already completed'}, 400

    # If GameRoom already exists for this match
    if match.game_room_id:
        room = GameRoom.query.get(match.game_room_id)
        if room:
            return match, {
                'message': 'Match room ready',
                'match_id': match.id,
                'game_room_id': room.id,
                'room_code': room.room_code,
                'status': match.status,
            }, 200

    # Generate a unique room code
    room_code = generate_room_code()

    game_manager = current_app.extensions.get('game_manager')
    if game_manager is None:
        return None, {'error': 'Game service is unavailable'}, 503

    # Tournament entry has already been paid.  This creates a real game room
    # without creating a second wager or BetSession.
    game_id, _ = game_manager.create_game(mode='local', card_count=match.card_count)

    # Create new GameRoom
    room = GameRoom(
        room_code=room_code,
        player1_id=match.player1_id,
        player2_id=match.player2_id,
        game_id=game_id,
        card_count=match.card_count,
        bet_amount=match.bet_amount,
        bet_type='tournament',
        tournament_id=tournament.id,
        match_id=match.id,
        is_tournament_game=True,
        status='in_progress',
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.session.add(room)
    db.session.flush()

    match.game_room_id = room.id
    match.status = 'in_progress'
    if not match.started_at:
        match.started_at = datetime.utcnow()

    deadline = datetime.utcnow() + timedelta(seconds=60)
    room.turn_deadline = deadline

    if tournament.status != 'in_progress':
        tournament.status = 'in_progress'

    db.session.commit()

    # Emit socket events to notify players and update tournament UI
    if _socketio:
        match_started_payload = {
            'tournament_id': tournament.id,
            'match_id': match.id,
            'room_code': room_code,
            'player1_id': match.player1_id,
            'player2_id': match.player2_id,
        }
        # Only the two players should be redirected into a playable room.
        # The tournament room still receives a generic refresh below.
        _socketio.emit('tournament_match_started', match_started_payload,
                       room=f'user_{match.player1_id}')
        _socketio.emit('tournament_match_started', match_started_payload,
                       room=f'user_{match.player2_id}')

    _emit_tournament_updated(tournament)

    return match, {
        'message': 'Tournament match started successfully',
        'match_id': match.id,
        'game_room_id': room.id,
        'room_code': room_code,
        'status': match.status,
    }, 200


@tournament_bp.route('/<int:tournament_id>/matches/<int:match_id>/start', methods=['POST'])
def start_match_endpoint(tournament_id, match_id):
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    match, response, status_code = start_tournament_match_helper(tournament_id, match_id, user_id=user_id)
    return jsonify(response), status_code


@tournament_bp.route('/<int:tournament_id>/matches/<int:match_id>/roll', methods=['POST'])
def roll_match_endpoint(tournament_id, match_id):
    """Start the 10-minute no-show roll for a tournament match.

    If the opponent does not join before the deadline, the waiting player wins
    the match by no-show (the absent player loses their entry stake).
    """
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    tournament = Tournament.query.get_or_404(tournament_id)
    match = TournamentMatch.query.filter_by(id=match_id, tournament_id=tournament.id).first()
    if match is None:
        return jsonify({'error': 'Match not found'}), 404
    if match.status in ('completed', 'cancelled'):
        return jsonify({'error': 'Match is already finished'}), 400
    if user_id not in {match.player1_id, match.player2_id}:
        return jsonify({'error': 'Only match participants can roll the game'}), 403

    # Rolling is not allowed when the opponent is already connected.
    from database import GameRoom
    if match.game_room_id:
        room = GameRoom.query.get(match.game_room_id)
        if room is not None:
            opponent_connected = room.player2_connected if match.player1_id == user_id else room.player1_connected
            if opponent_connected:
                return jsonify({'error': 'Your opponent is online — start the match instead'}), 400

    roll, payload = _start_roll(match, user_id)
    if payload is None:
        payload = {
            'match_id': match.id,
            'deadline': roll.deadline.isoformat(),
            'message': 'The roll is already active.',
        }
    return jsonify({
        'message': 'Roll started — the match will be awarded in 10 minutes if your opponent does not join.',
        'roll': payload,
    })


@tournament_bp.route('/<int:tournament_id>/matches/<int:match_id>/complete', methods=['POST'])
def complete_match(tournament_id, match_id):
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    user = User.query.get(user_id)
    if not (user and (user.is_admin or user.is_super_admin)):
        return jsonify({'error': 'Match results are server-authoritative'}), 403

    tournament = Tournament.query.get_or_404(tournament_id)
    match = TournamentMatch.query.filter_by(id=match_id, tournament_id=tournament.id).first_or_404()
    data = request.get_json(silent=True) or {}
    winner_id = data.get('winner_id') or data.get('winner_user_id')
    loser_id = data.get('loser_id') or data.get('loser_user_id')
    win_type = data.get('win_type')

    if not winner_id or not loser_id:
        return jsonify({'error': 'winner_id and loser_id are required'}), 400

    if winner_id not in {match.player1_id, match.player2_id} or loser_id not in {match.player1_id, match.player2_id}:
        return jsonify({'error': 'Winner and loser must belong to this match'}), 400

    match, err = record_tournament_match_result(
        match_id=match.id,
        winner_id=winner_id,
        loser_id=loser_id,
        win_type=win_type,
    )
    if err == "Match already completed":
        return jsonify({'message': err, 'match': {'id': match.id, 'status': match.status}})
    elif err:
        return jsonify({'error': err}), 400

    return jsonify({'message': 'Match completed', 'match': {'id': match.id, 'status': match.status}})


@tournament_bp.route('/<int:tournament_id>', methods=['GET'])
def get_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    participants = TournamentParticipant.query.filter_by(tournament_id=tournament.id).all()
    return jsonify({
        'tournament': tournament.to_dict(),
        'participants': [_serialize_participant(p) for p in participants],
    })
