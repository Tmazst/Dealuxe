"""
Multiplayer Game Controller using Flask-SocketIO
Handles real-time 2-player games, room management, and turn-based gameplay
"""
from flask import session, request
from flask_socketio import emit, join_room, leave_room, rooms
from datetime import datetime, timedelta
from database import db, GameRoom, User, BetSession, Player, get_player_by_user_id, Move
import json
from game.manager import GameManager
from controllers.flask_controller import FlaskGameController
import random
import string


# In-memory room cache for fast access
active_rooms = {}  # room_code -> {game_manager_ref, player_sockets, etc.}


def generate_room_code():
    """Generate unique 6-character room code"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not GameRoom.query.filter_by(room_code=code).first():
            return code


def init_multiplayer_events(socketio, game_manager, app=None):
    """Initialize all SocketIO event handlers"""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection - allow both authenticated and guest users"""
        user_id = session.get('user_id')
        if user_id:
            print(f"[MULTIPLAYER] User {user_id} connected - SID: {request.sid}")
            emit('connected', {'user_id': user_id, 'authenticated': True})
        else:
            print(f"[MULTIPLAYER] Guest user connected - SID: {request.sid}")
            emit('connected', {'authenticated': False})
        
        # Allow connection for both authenticated and guest users
        return True
    
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        user_id = session.get('user_id')
        if not user_id:
            return
        
        print(f"[MULTIPLAYER] User {user_id} disconnected - SID: {request.sid}")
        
        # Update last seen for all rooms user is in
        rooms_to_check = GameRoom.query.filter(
            db.or_(
                GameRoom.player1_id == user_id,
                GameRoom.player2_id == user_id
            ),
            GameRoom.status.in_(['in_progress', 'paused'])
        ).all()
        
        for room in rooms_to_check:
            if room.player1_id == user_id:
                room.player1_connected = False
                room.player1_last_seen = datetime.utcnow()
            elif room.player2_id == user_id:
                room.player2_connected = False
                room.player2_last_seen = datetime.utcnow()
            
            db.session.commit()
            
            # Notify opponent
            opponent_id = room.get_opponent_id(user_id)
            if opponent_id:
                socketio.emit('opponent_disconnected', {
                    'room_code': room.room_code,
                    'reconnection_window': 120  # 2 minutes
                }, room=f"user_{opponent_id}")
    
    
    @socketio.on('get_lobby')
    def handle_get_lobby():
        """Get list of available rooms - public access allowed"""
        from datetime import timedelta
        user_id = session.get('user_id')
        
        # Get waiting rooms created in last 5 hours (available to everyone)
        five_hours_ago = datetime.utcnow() - timedelta(hours=5)
        waiting_rooms = GameRoom.query.filter(
            GameRoom.status == 'waiting',
            GameRoom.created_at >= five_hours_ago
        ).order_by(GameRoom.created_at.desc()).limit(20).all()
        
        # Clean up expired rooms (older than 5 hours)
        expired_rooms = GameRoom.query.filter(
            GameRoom.status == 'waiting',
            GameRoom.created_at < five_hours_ago
        ).all()
        for room in expired_rooms:
            room.status = 'abandoned'
        if expired_rooms:
            db.session.commit()
        
        # Get user's active rooms (only if logged in)
        my_active_rooms = []
        if user_id:
            my_active_rooms = GameRoom.query.filter(
                db.or_(
                    GameRoom.player1_id == user_id,
                    GameRoom.player2_id == user_id
                ),
                GameRoom.status.in_(['in_progress', 'paused'])
            ).all()
        
        emit('lobby_data', {
            'available_rooms': [r.to_dict() for r in waiting_rooms],
            'my_active_rooms': [r.to_dict() for r in my_active_rooms]
        })
    
    
    @socketio.on('create_room')
    def handle_create_room(data):
        """Create a new game room"""
        print("Create a new game room")
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': 'Not authenticated'})
            return
        
        card_count = data.get('card_count', 6)
        bet_amount = data.get('bet_amount', 0)
        bet_type = data.get('bet_type', 'fake')
        
        # Get or create player profile
        player = get_player_by_user_id(user_id)
        if not player:
            emit('error', {'message': 'Player profile not found'})
            return
        
        # Auto-award free cash if needed for fake bets
        if bet_type == 'fake' and (not player.is_fake_cash_valid() or player.fake_balance < bet_amount):
            player.award_free_cash()
            db.session.commit()
        
        if not player.has_sufficient_balance(bet_amount, bet_type):
            emit('error', {'message': f'Insufficient {bet_type} balance. You have {player.fake_balance if bet_type == "fake" else player.real_balance}'})
            return
        
        # Create room
        room_code = generate_room_code()
        new_room = GameRoom(
            room_code=room_code,
            player1_id=user_id,
            card_count=card_count,
            bet_amount=bet_amount,
            bet_type=bet_type,
            status='waiting',
            player1_connected=True,
            player1_last_seen=datetime.utcnow()
        )
        
        db.session.add(new_room)
        db.session.commit()
        
        # Join SocketIO room
        join_room(room_code)
        join_room(f"user_{user_id}")
        
        print(f"[MULTIPLAYER] Room {room_code} created by user {user_id}")
        
        emit('room_created', {
            'room': new_room.to_dict(),
            'message': 'Waiting for opponent...'
        })
        
        # Broadcast to lobby (use to=None instead of broadcast=True)
        socketio.emit('lobby_updated', {}, to=None)
    
    
    @socketio.on('join_room')
    def handle_join_room(data):
        """Join an existing room"""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': 'Not authenticated'})
            return
        
        room_code = data.get('room_code')
        if not room_code:
            emit('error', {'message': 'Room code required'})
            return
        
        room = GameRoom.query.filter_by(room_code=room_code).first()
        if not room:
            emit('error', {'message': 'Room not found'})
            return
        
        if not room.can_join(user_id):
            emit('error', {'message': 'Cannot join this room'})
            return
        
        # Get or create player profile
        player = get_player_by_user_id(user_id)
        if not player:
            emit('error', {'message': 'Player profile not found'})
            return
        
        # Auto-award free cash if needed for fake bets
        if room.bet_type == 'fake' and (not player.is_fake_cash_valid() or player.fake_balance < room.bet_amount):
            player.award_free_cash()
            db.session.commit()
        
        if not player.has_sufficient_balance(room.bet_amount, room.bet_type):
            emit('error', {'message': f'Insufficient {room.bet_type} balance. You have {player.fake_balance if room.bet_type == "fake" else player.real_balance}'})
            return
        
        # Update room
        room.player2_id = user_id
        room.player2_connected = True
        room.player2_last_seen = datetime.utcnow()
        db.session.commit()
        
        # Join SocketIO room
        join_room(room_code)
        join_room(f"user_{user_id}")
        
        print(f"[MULTIPLAYER] User {user_id} joined room {room_code}")
        
        # Notify player 1
        player1_user = User.query.get(room.player1_id)
        player2_user = User.query.get(room.player2_id)
        
        socketio.emit('opponent_joined', {
            'room_code': room_code,
            'opponent_username': player2_user.username
        }, room=f"user_{room.player1_id}")
        
        emit('room_joined', {
            'room': room.to_dict(),
            'opponent_username': player1_user.username
        })
        
        # Start game
        socketio.emit('game_starting', {'countdown': 3}, room=room_code)
        socketio.start_background_task(start_game_countdown, room_code, socketio, game_manager, app)
    
    
    def start_game_countdown(room_code, socketio, game_manager, app):
        """Start game after countdown"""
        import time
        time.sleep(3)
        
        # Need application context for database access in background thread
        with app.app_context():
            room = GameRoom.query.filter_by(room_code=room_code).first()
            if not room or room.status != 'waiting':
                return
            
            # Deduct bets from both players
            player1 = get_player_by_user_id(room.player1_id)
            player2 = get_player_by_user_id(room.player2_id)
            
            if player1:
                player1.deduct_bet(room.bet_amount, room.bet_type)
            if player2:
                player2.deduct_bet(room.bet_amount, room.bet_type)
            
            # Create game via GameManager
            game_id, game_details = game_manager.create_game(mode="local", card_count=room.card_count)
            
            # Create bet session
            bet_session = BetSession(
                game_id=game_id,
                player_id=room.player1_id,
                opponent_id=room.player2_id,
                opponent_type='human',
                bet_type=room.bet_type,
                bet_amount=room.bet_amount,
                prize_pool=room.bet_amount * 2,
                card_count=room.card_count
            )
            db.session.add(bet_session)
            db.session.flush()
            
            # Update room
            room.game_id = game_id
            room.bet_session_id = bet_session.id
            room.status = 'in_progress'
            room.started_at = datetime.utcnow()
            room.current_turn_player = room.player1_id
            room.turn_deadline = datetime.utcnow() + timedelta(seconds=room.turn_duration_seconds)
            
            db.session.commit()
            
            # Store in memory
            active_rooms[room_code] = {
                'game_id': game_id,
                'manager': game_manager
            }
            
            print(f"[MULTIPLAYER] Game {game_id} started for room {room_code}")
            
            # Send game state to both players
            engine = game_manager.get_game(game_id)
            state = engine.get_state()
            
            # Get user IDs before leaving context
            player1_id = room.player1_id
            player2_id = room.player2_id
            turn_deadline_iso = room.turn_deadline.isoformat()
            
            # Player 1 is index 0, Player 2 is index 1
            # Prepare per-player transformed state to avoid leaking opponent private info
            def _is_my_turn(state_obj, player_index):
                phase = state_obj.get('phase')
                if phase == 'ATTACK':
                    return state_obj.get('attacker') == player_index
                if phase == 'DEFENSE':
                    return state_obj.get('defender') == player_index
                if phase == 'RULE_8':
                    return state_obj.get('attacker') == player_index
                return False

            base_state = {
                'phase': state.get('phase'),
                'attacker': state.get('attacker'),
                'defender': state.get('defender'),
                'attack_card': state.get('attack_card'),
                'attack_card_value': state.get('attack_card_value'),
                'game_over': state.get('game_over'),
                'winner': state.get('winner'),
                'ui_log': state.get('ui_log', []),
                'attack_pile': [state.get('attack_card')] if state.get('attack_card') else []
            }

            # Player 1 view: show full hand for player 1, only hand count for player 2
            p1_hand = state.get('hands', {}).get(0, [])
            p2_hand = state.get('hands', {}).get(1, [])
            transformed_p1 = dict(base_state)
            transformed_p1['players'] = [
                {'hand': p1_hand},
                {'hand_count': len(p2_hand)}
            ]

            # Player 2 view: show full hand for player 2, only hand count for player 1
            transformed_p2 = dict(base_state)
            transformed_p2['players'] = [
                {'hand_count': len(p1_hand)},
                {'hand': p2_hand}
            ]

            socketio.emit('game_started', {
                'game_id': game_id,
                'room_code': room_code,
                'your_player_index': 0,
                'your_turn': _is_my_turn(state, 0),
                'state': transformed_p1,
                'turn_deadline': turn_deadline_iso
            }, room=f"user_{player1_id}")

            socketio.emit('game_started', {
                'game_id': game_id,
                'room_code': room_code,
                'your_player_index': 1,
                'your_turn': _is_my_turn(state, 1),
                'state': transformed_p2,
                'turn_deadline': turn_deadline_iso
            }, room=f"user_{player2_id}")
            
            # Update lobby
            socketio.emit('lobby_updated', {}, to=None)
    
    
    @socketio.on('game_action')
    def handle_game_action(data):
        """Handle game action from player"""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': 'Not authenticated'})
            return
        
        room_code = data.get('room_code')
        action_type = data.get('action')
        action_data = data.get('data', {})
        
        room = GameRoom.query.filter_by(room_code=room_code).first()
        if not room:
            emit('error', {'message': 'Room not found'})
            return
        
        if room.status == 'paused':
            emit('error', {'message': 'Game is paused'})
            return
        
        if room.status != 'in_progress':
            emit('error', {'message': 'Game is not in progress'})
            return
        
        if not room.is_player_in_room(user_id):
            emit('error', {'message': 'You are not in this room'})
            return
        
        # Get game state to validate turn
        game_id = room.game_id
        engine = game_manager.get_game(game_id)
        state = engine.get_state()
        player_index = 0 if user_id == room.player1_id else 1

        # Idempotency: if client provided an idempotency_key, ensure we don't re-apply the same action
        idempotency_key = data.get('idempotency_key')
        if idempotency_key and room.bet_session_id:
            existing = Move.query.filter_by(idempotency_key=idempotency_key, bet_session_id=room.bet_session_id).first()
            if existing:
                print(f"[MULTIPLAYER] Duplicate action ignored for idempotency_key={idempotency_key}")
                # Send current state back to requester (masked)
                player_index = 0 if user_id == room.player1_id else 1
                # Build masked state
                p1_hand = state.get('hands', {}).get(0, [])
                p2_hand = state.get('hands', {}).get(1, [])
                base_state = {
                    'phase': state.get('phase'),
                    'attacker': state.get('attacker'),
                    'defender': state.get('defender'),
                    'attack_card': state.get('attack_card'),
                    'attack_card_value': state.get('attack_card_value'),
                    'game_over': state.get('game_over'),
                    'winner': state.get('winner'),
                    'ui_log': state.get('ui_log', []),
                    'attack_pile': [state.get('attack_card')] if state.get('attack_card') else []
                }
                transformed = dict(base_state)
                if player_index == 0:
                    transformed['players'] = [ {'hand': p1_hand}, {'hand_count': len(p2_hand)} ]
                else:
                    transformed['players'] = [ {'hand_count': len(p1_hand)}, {'hand': p2_hand} ]

                emit('game_update', {
                    'game_state': transformed,
                    'player_index': player_index,
                    'is_my_turn': transformed['attacker'] == player_index or transformed['defender'] == player_index,
                    'action': action_type,
                    'result': None,
                    'turn_deadline': room.turn_deadline.isoformat() if room.turn_deadline else None
                })
                return
        
        # Validate it's this player's turn based on phase and role
        phase = state.get('phase')
        is_valid_turn = False
        
        if phase == 'ATTACK':
            # Only attacker can act during ATTACK phase
            is_valid_turn = (state.get('attacker') == player_index)
        elif phase == 'DEFENSE':
            # Only defender can act during DEFENSE phase
            is_valid_turn = (state.get('defender') == player_index)
        elif phase == 'RULE_8':
            # Only attacker can act during RULE_8 phase
            is_valid_turn = (state.get('attacker') == player_index)
        
        if not is_valid_turn:
            print(f"[MULTIPLAYER] Invalid turn - User {user_id} (index {player_index}) tried to act during {phase} phase. Attacker: {state.get('attacker')}, Defender: {state.get('defender')}")
            emit('error', {'message': 'Not your turn'})
            return
        
        # Check turn deadline - if expired, auto-play a safe action
        if room.turn_deadline and datetime.utcnow() > room.turn_deadline:
            print(f"[MULTIPLAYER] Turn expired for user {user_id} - auto-playing action")
            
            # Auto-play based on phase (state and player_index already fetched above)
            if state.get('phase') == 'DEFENSE' and state.get('defender') == player_index:
                # Auto-draw if defending
                print(f"[MULTIPLAYER] Auto-draw for expired defense turn")
                action_type = 'draw'
            elif state.get('phase') == 'ATTACK' and state.get('attacker') == player_index:
                # Auto-skip or play first card if attacking
                print(f"[MULTIPLAYER] Auto-attack with first card for expired attack turn")
                action_data = {'index': 0}  # Attack with first card
                action_type = 'attack'
            else:
                # Shouldn't happen, but emit error and return
                emit('error', {'message': 'Turn expired - unable to auto-play'})
                return
            
            # Emit notification to both players
            socketio.emit('turn_timeout', {
                'message': f'Player {player_index + 1} ran out of time - auto-playing',
                'player_index': player_index
            }, room=room_code)
            
            # Continue with auto-action (don't return here)
        
        # Get game engine
        game_id = room.game_id
        engine = game_manager.get_game(game_id)
        # For multiplayer we must NOT run the local AI; pass run_ai=False so the
        # FlaskGameController does not invoke the SimpleAIController.
        controller = FlaskGameController(engine, run_ai=False)
        
        # Determine player index
        player_index = 0 if user_id == room.player1_id else 1
        
        # Execute action
        actor_index = player_index  # Track which player performed the action for client-side animations
        result = None
        try:
            if action_type == 'attack':
                result = controller.attack(action_data.get('index'))
            elif action_type == 'defend':
                result = controller.defend(action_data.get('i1'), action_data.get('i2'))
            elif action_type == 'draw':
                result = controller.draw()
            elif action_type == 'rule8_drop':
                result = controller.rule_8_drop(action_data.get('value'))
            elif action_type == 'rule8_crash':
                result = controller.rule_8_crash(action_data.get('crash'))
            else:
                emit('error', {'message': 'Invalid action'})
                return
        except Exception as e:
            print(f"[MULTIPLAYER] Error executing action: {e}")
            emit('error', {'message': str(e)})
            return

        # Persist updated engine state back to manager (important for Redis-backed storage)
        try:
            game_manager.update_game(game_id, engine)
        except Exception as e:
            print(f"[MULTIPLAYER] Warning: failed to persist game state: {e}")

        # Get updated state
        state = engine.get_state()
        
        # Transform state base to be used for per-player masking
        base_state = {
            'phase': state.get('phase'),
            'attacker': state.get('attacker'),
            'defender': state.get('defender'),
            'attack_card': state.get('attack_card'),
            'attack_card_value': state.get('attack_card_value'),
            'game_over': state.get('game_over'),
            'winner': state.get('winner'),
            'ui_log': state.get('ui_log', []),
            'attack_pile': [state.get('attack_card')] if state.get('attack_card') else []
        }
        
        # Persist move to DB (seq_num, idempotency, payload, snapshot)
        try:
            # Determine player record (players table) for logging
            player_record = get_player_by_user_id(user_id)
            last_seq = db.session.query(db.func.max(Move.seq_num)).filter_by(bet_session_id=room.bet_session_id).scalar() or 0
            seq_num = int(last_seq) + 1
            move = Move(
                bet_session_id=room.bet_session_id,
                game_session_id=room.game_id if isinstance(room.game_id, int) else None,
                seq_num=seq_num,
                player_id=player_record.id if player_record else None,
                action_type=action_type,
                action_payload=json.dumps(action_data) if action_data is not None else None,
                result_snapshot=json.dumps(state),
                idempotency_key=idempotency_key
            )
            db.session.add(move)
            db.session.commit()
        except Exception as e:
            print(f"[MULTIPLAYER] Failed to persist move: {e}")
            db.session.rollback()

        # Update turn
        room.current_turn_player = room.player1_id if state['attacker'] == 0 else room.player2_id
        room.turn_deadline = datetime.utcnow() + timedelta(seconds=room.turn_duration_seconds)
        db.session.commit()
        
        # Check if game over
        if state.get('game_over'):
            handle_game_over(room, state, socketio)
            return
        
        # Broadcast state to both players with per-player masking
        p1_hand = state.get('hands', {}).get(0, [])
        p2_hand = state.get('hands', {}).get(1, [])

        transformed_p1 = dict(base_state)
        transformed_p1['players'] = [ {'hand': p1_hand}, {'hand_count': len(p2_hand)} ]

        transformed_p2 = dict(base_state)
        transformed_p2['players'] = [ {'hand_count': len(p1_hand)}, {'hand': p2_hand} ]

        for pid, transformed in [(room.player1_id, transformed_p1), (room.player2_id, transformed_p2)]:
            if not pid:
                continue
            player_index = 0 if pid == room.player1_id else 1
            is_my_turn = transformed['attacker'] == player_index or transformed['defender'] == player_index
            print(f"[MULTIPLAYER] Broadcasting game_update to user_{pid} (player_index={player_index})")
            socketio.emit('game_update', {
                'game_state': transformed,
                'player_index': player_index,
                'actor_index': actor_index,
                'is_my_turn': is_my_turn,
                'action': action_type,
                'result': result.get_json() if hasattr(result, 'get_json') else result,
                'turn_deadline': room.turn_deadline.isoformat()
            }, room=f"user_{pid}")
            print(f"[MULTIPLAYER] Emitted game_update to user_{pid}")
    
    
    def handle_game_over(room, state, socketio):
        """Handle game completion: finalize session, award DB balances, and notify clients"""
        winner_index = state.get('winner')
        winner_id = room.player1_id if winner_index == 0 else room.player2_id
        loser_id = room.player2_id if winner_index == 0 else room.player1_id

        room.status = 'completed'
        room.winner_id = winner_id
        room.completed_at = datetime.utcnow()

        winnings_awarded = 0.0
        new_balances = {}

        # Update bet session and award winnings using DB-backed Player
        if room.bet_session_id:
            bet_session = BetSession.query.get(room.bet_session_id)
            if bet_session:
                from database import get_player_by_user_id
                # Award prize pool to winner
                winner_player_db = get_player_by_user_id(winner_id)
                loser_player_db = get_player_by_user_id(loser_id)
                if winner_player_db:
                    winnings_awarded = float(bet_session.prize_pool or 0)
                    winner_player_db.award_winnings(winnings_awarded, bet_session.bet_type)
                    winner_player_db.record_game_result(won=True)
                    new_balances[winner_id] = {
                        'real': winner_player_db.real_balance,
                        'fake': winner_player_db.fake_balance,
                        'fake_expires_at': winner_player_db.fake_balance_expires_at.isoformat() if winner_player_db.fake_balance_expires_at else None
                    }
                if loser_player_db:
                    loser_player_db.record_game_result(won=False)
                    new_balances[loser_id] = {
                        'real': loser_player_db.real_balance,
                        'fake': loser_player_db.fake_balance,
                        'fake_expires_at': loser_player_db.fake_balance_expires_at.isoformat() if loser_player_db.fake_balance_expires_at else None
                    }

                bet_session.status = 'completed'
                bet_session.winner_id = winner_id
                bet_session.completed_at = datetime.utcnow()

        db.session.commit()

        # Remove from active rooms
        if room.room_code in active_rooms:
            del active_rooms[room.room_code]

        print(f"[MULTIPLAYER] Game completed in room {room.room_code}, winner: {winner_id}")

        # Broadcast general game_over info to room
        socketio.emit('game_over', {
            'winner_id': winner_id,
            'winner_index': winner_index,
            'state': state,
            'prize_pool': room.bet_amount * 2 if room.bet_session_id else 0
        }, room=room.room_code)

        # Send personal balance updates to each user privately
        try:
            if winner_id in new_balances:
                socketio.emit('game_over_personal', {
                    'your_user_id': winner_id,
                    'your_new_balance': new_balances[winner_id],
                    'winnings_awarded': winnings_awarded
                }, room=f"user_{winner_id}")
            if loser_id in new_balances:
                socketio.emit('game_over_personal', {
                    'your_user_id': loser_id,
                    'your_new_balance': new_balances[loser_id],
                    'winnings_awarded': 0
                }, room=f"user_{loser_id}")
        except Exception as e:
            print(f"[MULTIPLAYER] Failed to emit personal balances: {e}")
    
    
    @socketio.on('request_pause')
    def handle_request_pause(data):
        """Request to pause the game"""
        user_id = session.get('user_id')
        room_code = data.get('room_code')
        
        room = GameRoom.query.filter_by(room_code=room_code).first()
        if not room or room.status != 'in_progress':
            emit('error', {'message': 'Cannot pause game'})
            return
        
        if not room.is_player_in_room(user_id):
            emit('error', {'message': 'You are not in this room'})
            return
        
        room.pause_requested_by = user_id
        db.session.commit()
        
        opponent_id = room.get_opponent_id(user_id)
        
        # Ask opponent for approval
        socketio.emit('pause_requested', {
            'requester_id': user_id,
            'room_code': room_code
        }, room=f"user_{opponent_id}")
        
        emit('pause_request_sent', {'message': 'Waiting for opponent approval...'})
    
    
    @socketio.on('approve_pause')
    def handle_approve_pause(data):
        """Approve pause request"""
        user_id = session.get('user_id')
        room_code = data.get('room_code')
        approved = data.get('approved', False)
        
        room = GameRoom.query.filter_by(room_code=room_code).first()
        if not room or room.status != 'in_progress':
            return
        
        if not room.is_player_in_room(user_id):
            return
        
        if not approved:
            # Pause rejected
            room.pause_requested_by = None
            db.session.commit()
            
            socketio.emit('pause_rejected', {}, room=room_code)
            return
        
        # Pause approved
        room.status = 'paused'
        room.pause_approved_by = user_id
        room.paused_at = datetime.utcnow()
        db.session.commit()
        
        socketio.emit('game_paused', {
            'paused_at': room.paused_at.isoformat()
        }, room=room_code)
    
    
    @socketio.on('resume_game')
    def handle_resume_game(data):
        """Resume paused game"""
        user_id = session.get('user_id')
        room_code = data.get('room_code')
        
        room = GameRoom.query.filter_by(room_code=room_code).first()
        if not room or room.status != 'paused':
            emit('error', {'message': 'Game is not paused'})
            return
        
        if not room.is_player_in_room(user_id):
            return
        
        # Both players must be connected to resume
        if not (room.player1_connected and room.player2_connected):
            emit('error', {'message': 'Both players must be online to resume'})
            return
        
        room.status = 'in_progress'
        room.pause_requested_by = None
        room.pause_approved_by = None
        room.paused_at = None
        # Reset turn deadline
        room.turn_deadline = datetime.utcnow() + timedelta(seconds=room.turn_duration_seconds)
        db.session.commit()
        
        socketio.emit('game_resumed', {
            'turn_deadline': room.turn_deadline.isoformat()
        }, room=room_code)
    
    
    @socketio.on('reconnect_to_room')
    def handle_reconnect(data):
        """Reconnect to an active game"""
        try:
            user_id = session.get('user_id')
            room_code = data.get('room_code')
            
            print(f"[MULTIPLAYER] Reconnect attempt - User: {user_id}, Room: {room_code}")
            
            if not user_id:
                emit('error', {'message': 'Not authenticated'})
                return
            
            room = GameRoom.query.filter_by(room_code=room_code).first()
            if not room:
                print(f"[MULTIPLAYER] Room {room_code} not found")
                emit('error', {'message': 'Room not found'})
                return
            
            if not room.is_player_in_room(user_id):
                print(f"[MULTIPLAYER] User {user_id} not in room {room_code}")
                emit('error', {'message': 'You are not in this room'})
                return
            
            # Update connection status
            if room.player1_id == user_id:
                room.player1_connected = True
                room.player1_last_seen = datetime.utcnow()
                player_index = 0
            elif room.player2_id == user_id:
                room.player2_connected = True
                room.player2_last_seen = datetime.utcnow()
                player_index = 1
            else:
                emit('error', {'message': 'Invalid player'})
                return
            
            db.session.commit()
            
            # Rejoin rooms
            join_room(room_code)
            join_room(f"user_{user_id}")
            
            print(f"[MULTIPLAYER] User {user_id} reconnected to room {room_code}, Game ID: {room.game_id}")
            
            # Send current game state
            if room.game_id:
                try:
                    engine = game_manager.get_game(room.game_id)
                except KeyError:
                    # Game not found in manager - recreate it
                    print(f"[MULTIPLAYER] Game {room.game_id} not in manager, recreating...")
                    try:
                        # Recreate the game with the same settings
                        game_id, game_details = game_manager.create_game(mode="local", card_count=room.card_count)
                        # Update room with new game ID
                        room.game_id = game_id
                        db.session.commit()
                        engine = game_manager.get_game(game_id)
                        print(f"[MULTIPLAYER] Game recreated with new ID: {game_id}")
                    except Exception as e:
                        print(f"[MULTIPLAYER] ERROR recreating game: {e}")
                        emit('error', {'message': 'Failed to recreate game'})
                        return
                
                state = engine.get_state()

                # Build a masked state for the reconnecting user:
                # - Show full hand only for the reconnecting player's index
                # - Show only hand_count for the opponent
                base_state = {
                    'phase': state.get('phase'),
                    'attacker': state.get('attacker'),
                    'defender': state.get('defender'),
                    'attack_card': state.get('attack_card'),
                    'attack_card_value': state.get('attack_card_value'),
                    'game_over': state.get('game_over'),
                    'winner': state.get('winner'),
                    'ui_log': state.get('ui_log', []),
                    'attack_pile': [state.get('attack_card')] if state.get('attack_card') else []
                }

                p1_hand = state.get('hands', {}).get(0, [])
                p2_hand = state.get('hands', {}).get(1, [])

                transformed_state = dict(base_state)
                if player_index == 0:
                    transformed_state['players'] = [
                        {'hand': p1_hand},
                        {'hand_count': len(p2_hand)}
                    ]
                else:
                    transformed_state['players'] = [
                        {'hand_count': len(p1_hand)},
                        {'hand': p2_hand}
                    ]

                is_my_turn = transformed_state['attacker'] == player_index or transformed_state['defender'] == player_index
                
                print(f"[MULTIPLAYER] Sending game state to user {user_id}, player index {player_index}")
                
                emit('game_update', {
                    'game_state': transformed_state,
                    'player_index': player_index,
                    'actor_index': None,  # reconnect update has no immediate actor
                    'is_my_turn': is_my_turn,
                    'turn_deadline': room.turn_deadline.isoformat() if room.turn_deadline else None,
                    'room_code': room_code,
                    'game_id': room.game_id
                })
                
                # Notify opponent
                opponent_id = room.get_opponent_id(user_id)
                if opponent_id:
                    socketio.emit('opponent_reconnected', {
                        'room_code': room_code
                    }, room=f"user_{opponent_id}")
            else:
                print(f"[MULTIPLAYER] ERROR: Room {room_code} has no game_id")
                emit('error', {'message': 'Game not started yet'})
                
        except Exception as e:
            print(f"[MULTIPLAYER] ERROR in reconnect_to_room: {e}")
            import traceback
            traceback.print_exc()
            emit('error', {'message': f'Server error: {str(e)}'})
        else:
            emit('reconnected', {'room': room.to_dict()})
    
    
    return socketio
