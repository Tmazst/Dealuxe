"""
Session Controller
Handles bet session creation, completion, and player balance management
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid

from config import GameConfig
from models.player import get_or_create_demo_player, get_player
from models.bet_session import create_session, get_session_by_game, get_session

session_bp = Blueprint('session', __name__)


@session_bp.route('/api/session/create', methods=['POST'])
def create_game_session():
    """
    Create a new game session with betting
    
    Request JSON:
        opponent_type: 'ai' or 'human'
        card_count: int (number of cards per player)
        bet_type: 'real' or 'fake'
        bet_amount: float (amount to bet)
        player_id: str (optional, uses demo player if not provided)
    
    Response JSON:
        success: bool
        session_id: str
        game_id: str
        player_balance: dict
        error: str (if success=False)
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        opponent_type = data.get('opponent_type')
        card_count = data.get('card_count')
        bet_type = data.get('bet_type')
        bet_amount = data.get('bet_amount')
        
        if not all([opponent_type, card_count, bet_type is not None, bet_amount is not None]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        # Validate opponent type
        if opponent_type not in ['ai', 'human']:
            return jsonify({
                'success': False,
                'error': 'Invalid opponent type'
            }), 400
        
        # Validate bet type
        if bet_type not in ['real', 'fake']:
            return jsonify({
                'success': False,
                'error': 'Invalid bet type'
            }), 400
        
        # Get or create player
        player_id = data.get('player_id')
        if not player_id:
            player = get_or_create_demo_player()
            player_id = player.id
        else:
            player = get_player(player_id)
            if not player:
                return jsonify({
                    'success': False,
                    'error': 'Player not found'
                }), 404
        
        # Check if player has sufficient balance
        if not player.has_sufficient_balance(bet_amount, bet_type):
            # Check if free cash expired
            if bet_type == 'fake' and player.fake_balance_expires_at:
                if datetime.now() > player.fake_balance_expires_at:
                    return jsonify({
                        'success': False,
                        'error': 'Free cash expired. Please claim new free cash.'
                    }), 400
            
            return jsonify({
                'success': False,
                'error': f'Insufficient {bet_type} balance'
            }), 400
        
        # Deduct bet from player balance
        player.deduct_bet(bet_amount, bet_type)
        
        # Generate game ID (will be replaced with actual game ID from engine)
        game_id = str(uuid.uuid4())
        
        # Create bet session
        session = create_session(
            game_id=game_id,
            player_id=player_id,
            opponent_type=opponent_type,
            bet_type=bet_type,
            bet_amount=bet_amount
        )
        
        return jsonify({
            'success': True,
            'session_id': session.id,
            'game_id': game_id,
            'player_balance': {
                'real': player.real_balance,
                'fake': player.fake_balance,
                'fake_expires_at': player.fake_balance_expires_at.isoformat() if player.fake_balance_expires_at else None
            },
            'prize_pool': session.prize_pool
        }), 200
        
    except Exception as e:
        print(f"[SESSION] Error creating session: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@session_bp.route('/api/session/complete', methods=['POST'])
def complete_game_session():
    """
    Complete a game session and award winnings
    
    Request JSON:
        game_id: str
        winner_id: str (player_id or 'ai')
    
    Response JSON:
        success: bool
        winnings_awarded: float
        new_balance: dict
        error: str (if success=False)
    """
    try:
        data = request.get_json()
        
        game_id = data.get('game_id')
        winner_id = data.get('winner_id')
        
        if not game_id or not winner_id:
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        # Get session
        session = get_session_by_game(game_id)
        if not session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        # Complete session
        session.complete_session(winner_id)
        
        # Award winnings if player won
        winnings_awarded = 0
        new_balance = None
        
        if session.player_won(session.player_id):
            player = get_player(session.player_id)
            if player:
                winnings_awarded = session.prize_pool
                player.award_winnings(winnings_awarded, session.bet_type)
                player.record_game_result(won=True)
                
                new_balance = {
                    'real': player.real_balance,
                    'fake': player.fake_balance,
                    'fake_expires_at': player.fake_balance_expires_at.isoformat() if player.fake_balance_expires_at else None
                }
        else:
            # Player lost, just record result
            player = get_player(session.player_id)
            if player:
                player.record_game_result(won=False)
                
                new_balance = {
                    'real': player.real_balance,
                    'fake': player.fake_balance,
                    'fake_expires_at': player.fake_balance_expires_at.isoformat() if player.fake_balance_expires_at else None
                }
        
        return jsonify({
            'success': True,
            'winnings_awarded': winnings_awarded,
            'new_balance': new_balance
        }), 200
        
    except Exception as e:
        print(f"[SESSION] Error completing session: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@session_bp.route('/api/player/balance', methods=['GET'])
def get_player_balance():
    """
    Get player balance and wallet info
    
    Query params:
        player_id: str (optional, uses demo player if not provided)
    
    Response JSON:
        success: bool
        balance: dict
        error: str (if success=False)
    """
    try:
        player_id = request.args.get('player_id')
        
        # Get or create player
        if not player_id:
            player = get_or_create_demo_player()
        else:
            player = get_player(player_id)
            if not player:
                return jsonify({
                    'success': False,
                    'error': 'Player not found'
                }), 404
        
        # Check if free cash expired
        free_cash_expired = False
        if player.fake_balance_expires_at:
            if datetime.utcnow() > player.fake_balance_expires_at:
                free_cash_expired = True
        
        return jsonify({
            'success': True,
            'balance': {
                'real': player.real_balance,
                'fake': player.fake_balance,
                'fake_expires_at': player.fake_balance_expires_at.isoformat() if player.fake_balance_expires_at else None,
                'free_cash_expired': free_cash_expired
            },
            'stats': {
                'total_games': player.total_games,
                'wins': player.wins,
                'losses': player.losses,
                'win_rate': player.get_win_rate()
            }
        }), 200
        
    except Exception as e:
        print(f"[SESSION] Error getting balance: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@session_bp.route('/api/player/claim-free-cash', methods=['POST'])
def claim_free_cash():
    """
    Claim free cash for player (if expired or first time)
    
    Request JSON:
        player_id: str (optional, uses demo player if not provided)
    
    Response JSON:
        success: bool
        amount_awarded: float
        target_amount: float
        expires_at: str (ISO format)
        new_balance: dict
        error: str (if success=False)
    """
    try:
        data = request.get_json()
        player_id = data.get('player_id') if data else None
        
        # Get or create player
        if not player_id:
            player = get_or_create_demo_player()
        else:
            player = get_player(player_id)
            if not player:
                return jsonify({
                    'success': False,
                    'error': 'Player not found'
                }), 404
        
        # Check if free cash already active
        if player.fake_balance_expires_at:
            if datetime.utcnow() < player.fake_balance_expires_at:
                time_remaining = (player.fake_balance_expires_at - datetime.utcnow()).total_seconds()
                hours_remaining = time_remaining / 3600
                
                return jsonify({
                    'success': False,
                    'error': f'Free cash still active. {hours_remaining:.1f} hours remaining.'
                }), 400
        
        # Award free cash
        amount_awarded, target_amount = player.award_free_cash()
        
        return jsonify({
            'success': True,
            'amount_awarded': amount_awarded,
            'target_amount': target_amount,
            'expires_at': player.fake_balance_expires_at.isoformat(),
            'new_balance': {
                'real': player.real_balance,
                'fake': player.fake_balance,
                'fake_expires_at': player.fake_balance_expires_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        print(f"[SESSION] Error claiming free cash: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
