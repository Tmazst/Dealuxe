from datetime import datetime
import random

from flask import Blueprint, request, jsonify, session

from database import (
    db,
    Tournament,
    TournamentParticipant,
    TournamentBracket,
    TournamentMatch,
    TournamentPrizePool,
    User,
    Player,
    create_tournament_record,
    add_tournament_participant,
    log_transaction,
)


tournament_bp = Blueprint('tournament', __name__, url_prefix='/api/tournaments')

# Official prize split: 1st = 50%, 2nd = 12.5%, 3rd = 6%  (scope + schema doc)
PRIZE_PERCENTAGES = {1: 0.50, 2: 0.125, 3: 0.06}


def _get_current_user_id():
    return session.get('user_id')


def _charge_tournament_entry(user_id, amount, tournament_id):
    """Charge a user for tournament entry when wallet balance is available."""
    player = Player.query.filter_by(user_id=user_id).first()
    if player is None:
        return True, None

    if player.real_balance < amount:
        return False, 'Insufficient balance'

    balance_before = player.real_balance
    player.real_balance -= amount
    player.total_wagered += amount
    log_transaction(
        player_id=player.id,
        transaction_type='tournament_entry',
        amount=amount,
        balance_type='real',
        balance_before=balance_before,
        balance_after=player.real_balance,
        description=f'Tournament entry #{tournament_id}',
        tournament_id=tournament_id,
    )
    return True, None


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

    # Third-place playoff fed by the two semi-final losers.
    if total_rounds >= 2:
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
                transaction_type='prize_award',
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


@tournament_bp.route('', methods=['GET'])
def list_tournaments():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return jsonify({'tournaments': [t.to_dict() for t in tournaments]})


@tournament_bp.route('/create', methods=['POST'])
def create_tournament():
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    tournament_type = data.get('tournament_type', 'standard')
    tournament_name = data.get('tournament_name') or f"{tournament_type.title()} Tournament"
    entry_fee = float(data.get('entry_fee', 10.0))
    max_players = int(data.get('max_players') or {'standard': 4, 'premium': 8, 'deluxe': 16}.get(tournament_type, 4))

    if tournament_type not in {'standard', 'premium', 'deluxe'}:
        return jsonify({'error': 'Invalid tournament type'}), 400

    paid, error_message = _charge_tournament_entry(user_id, entry_fee, None)
    if not paid:
        return jsonify({'error': error_message}), 402

    tournament = create_tournament_record(
        creator_id=user_id,
        tournament_type=tournament_type,
        tournament_name=tournament_name,
        entry_fee=entry_fee,
        max_players=max_players,
        is_auto_lock=data.get('is_auto_lock', False),
        locked_player_count=data.get('locked_player_count'),
    )
    add_tournament_participant(tournament.id, user_id, payment_status='completed', paid_amount=entry_fee, payment_method='wallet')
    tournament.current_player_count = 1
    tournament.prize_pool_amount = entry_fee
    _ensure_prize_pool(tournament)
    db.session.commit()

    return jsonify({'tournament': tournament.to_dict(), 'message': 'Tournament created'})


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

    paid, error_message = _charge_tournament_entry(user_id, tournament.entry_fee, tournament.id)
    if not paid:
        return jsonify({'error': error_message}), 402

    participant = add_tournament_participant(tournament.id, user_id, payment_status='completed', paid_amount=tournament.entry_fee, payment_method='wallet')
    tournament.current_player_count += 1
    tournament.prize_pool_amount += tournament.entry_fee
    _ensure_prize_pool(tournament)

    if tournament.current_player_count >= tournament.max_players and tournament.is_auto_lock:
        tournament.status = 'locked'
        tournament.locked_at = datetime.utcnow()
        tournament.locked_player_count = tournament.current_player_count
        _build_bracket(tournament)
    db.session.commit()

    return jsonify({'message': 'Joined tournament', 'participant': {'id': participant.id, 'user_id': user_id}})


@tournament_bp.route('/<int:tournament_id>/lock', methods=['POST'])
def lock_tournament(tournament_id):
    user_id = _get_current_user_id()
    tournament = Tournament.query.get_or_404(tournament_id)

    # Restrict manual locking to the creator (or an admin).
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    if tournament.creator_id != user_id:
        user = User.query.get(user_id)
        if not (user and user.is_admin):
            return jsonify({'error': 'Only the creator can lock this tournament'}), 403

    if tournament.status in {'locked', 'in_progress', 'completed', 'cancelled'}:
        return jsonify({'error': 'Tournament already locked or completed'}), 400

    if tournament.current_player_count < 2:
        return jsonify({'error': 'Need at least 2 players to lock'}), 400

    tournament.status = 'locked'
    tournament.locked_at = datetime.utcnow()
    tournament.locked_player_count = tournament.current_player_count
    _build_bracket(tournament)

    return jsonify({'message': 'Tournament locked', 'tournament': tournament.to_dict()})


@tournament_bp.route('/<int:tournament_id>/generate-bracket', methods=['POST'])
def generate_bracket(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    if tournament.status not in {'locked', 'open'}:
        return jsonify({'error': 'Tournament must be open or locked'}), 400

    brackets = _build_bracket(tournament)
    return jsonify({'message': 'Bracket generated', 'bracket_count': len(brackets)})


@tournament_bp.route('/<int:tournament_id>/matches/<int:match_id>/complete', methods=['POST'])
def complete_match(tournament_id, match_id):
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

    if match.status == 'completed':
        return jsonify({'message': 'Match already completed', 'match': {'id': match.id, 'status': match.status}})

    now = datetime.utcnow()
    if match.started_at is None:
        match.started_at = now

    match.status = 'completed'
    match.winner_id = winner_id
    match.loser_id = loser_id
    match.win_type = win_type
    match.completed_at = now
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
    return jsonify({'message': 'Match completed', 'match': {'id': match.id, 'status': match.status}})


@tournament_bp.route('/<int:tournament_id>', methods=['GET'])
def get_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return jsonify({'tournament': tournament.to_dict()})

