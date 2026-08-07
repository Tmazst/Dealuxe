from datetime import datetime

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
    pool = TournamentPrizePool.query.filter_by(tournament_id=tournament.id).first()
    if pool is not None:
        return pool

    pool = TournamentPrizePool(
        tournament_id=tournament.id,
        amount=tournament.prize_pool_amount,
        first_place_amount=tournament.prize_pool_amount * 0.6,
        second_place_amount=tournament.prize_pool_amount * 0.3,
        third_place_amount=tournament.prize_pool_amount * 0.1,
    )
    db.session.add(pool)
    db.session.flush()
    return pool


def _build_bracket(tournament):
    """Create bracket rows and match records for a tournament."""
    existing_brackets = TournamentBracket.query.filter_by(tournament_id=tournament.id).all()
    if existing_brackets:
        return existing_brackets

    participants = TournamentParticipant.query.filter_by(tournament_id=tournament.id).order_by(TournamentParticipant.registered_at.asc()).all()
    if len(participants) < 2:
        return []

    bracket_size = 4
    while bracket_size < len(participants):
        bracket_size *= 2

    seeded_users = [participant.user_id for participant in participants]
    while len(seeded_users) < bracket_size:
        seeded_users.append(None)

    round_number = 1
    current_matches = bracket_size // 2
    while current_matches > 0:
        for match_number in range(1, current_matches + 1):
            bracket = TournamentBracket(
                tournament_id=tournament.id,
                round_number=round_number,
                round_name='Round 1' if round_number == 1 else f'Round {round_number}',
                match_number=match_number,
                player1_id=seeded_users[(match_number - 1) * 2] if round_number == 1 else None,
                player2_id=seeded_users[(match_number - 1) * 2 + 1] if round_number == 1 else None,
                status='scheduled' if round_number == 1 and seeded_users[(match_number - 1) * 2] is not None and seeded_users[(match_number - 1) * 2 + 1] is not None else 'pending',
            )
            db.session.add(bracket)
            db.session.flush()

            match = TournamentMatch(
                tournament_id=tournament.id,
                bracket_id=bracket.id,
                player1_id=bracket.player1_id,
                player2_id=bracket.player2_id,
                status='scheduled' if round_number == 1 and bracket.player1_id is not None and bracket.player2_id is not None else 'pending',
                card_count=6,
                bet_amount=tournament.entry_fee,
            )
            db.session.add(match)
            bracket.match_id = match.id

        current_matches //= 2
        round_number += 1

    tournament.status = 'in_progress'
    tournament.started_at = datetime.utcnow()
    db.session.commit()
    return TournamentBracket.query.filter_by(tournament_id=tournament.id).all()


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
    tournament = Tournament.query.get_or_404(tournament_id)
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

    if not winner_id or not loser_id:
        return jsonify({'error': 'winner_id and loser_id are required'}), 400

    if winner_id not in {match.player1_id, match.player2_id} or loser_id not in {match.player1_id, match.player2_id}:
        return jsonify({'error': 'Winner and loser must belong to this match'}), 400

    match.status = 'completed'
    match.winner_id = winner_id
    match.loser_id = loser_id
    match.completed_at = datetime.utcnow()
    match.duration_seconds = int((match.completed_at - (match.started_at or match.completed_at)).total_seconds()) if match.started_at else 0

    bracket = TournamentBracket.query.get(match.bracket_id)
    if bracket is not None:
        bracket.status = 'completed'
        bracket.winner_id = winner_id
        bracket.completed_at = datetime.utcnow()

    winner_participant = TournamentParticipant.query.filter_by(tournament_id=tournament.id, user_id=winner_id).first()
    loser_participant = TournamentParticipant.query.filter_by(tournament_id=tournament.id, user_id=loser_id).first()
    if winner_participant is not None:
        winner_participant.status = 'active'
    if loser_participant is not None:
        loser_participant.status = 'eliminated'

    if bracket is not None:
        next_round = bracket.round_number + 1
        next_bracket = TournamentBracket.query.filter_by(
            tournament_id=tournament.id,
            round_number=next_round,
            match_number=(bracket.match_number + 1) // 2,
        ).first()
        if next_bracket is not None:
            if next_bracket.player1_id is None:
                next_bracket.player1_id = winner_id
            elif next_bracket.player2_id is None:
                next_bracket.player2_id = winner_id

            next_match = TournamentMatch.query.filter_by(bracket_id=next_bracket.id).first()
            if next_match is not None:
                next_match.player1_id = next_bracket.player1_id
                next_match.player2_id = next_bracket.player2_id
                next_match.status = 'scheduled' if next_bracket.player1_id is not None and next_bracket.player2_id is not None else 'pending'

    if bracket is not None and bracket.round_number >= TournamentBracket.query.filter_by(tournament_id=tournament.id).order_by(TournamentBracket.round_number.desc()).first().round_number:
        tournament.status = 'completed'
        tournament.completed_at = datetime.utcnow()
        tournament.winner_id = winner_id
        tournament.runner_up_id = loser_id

    db.session.commit()
    return jsonify({'message': 'Match completed', 'match': {'id': match.id, 'status': match.status}})


@tournament_bp.route('/<int:tournament_id>', methods=['GET'])
def get_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return jsonify({'tournament': tournament.to_dict()})
