"""
Authentication and User Management Routes
"""
from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database import (
    db, User, Player, create_user, 
    get_user_by_username, get_user_by_email,
    get_player_by_user_id
)
from Forms import LoginForm, RegistrationForm
from functools import wraps

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new user (handles both form and API requests)"""
    # Check if this is a JSON API request
    if request.is_json:
        return register_api_internal()
    
    # Handle form submission
    form = RegistrationForm()
    
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        phone = form.phone.data
        full_name = form.name.data
        
        # Check if username exists
        if get_user_by_username(username):
            flash('Username already exists', 'error')
            return render_template('register.html', form=form)
        
        # Check if email exists
        if get_user_by_email(email):
            flash('Email already exists', 'error')
            return render_template('register.html', form=form)
        
        try:
            # Create user and player
            user, player = create_user(
                username=username,
                email=email,
                password=password,
                phone=phone,
                full_name=full_name
            )
            
            # Award welcome bonus (free cash)
            player.award_free_cash()
            
            # Log user in
            session['user_id'] = user.id
            session['username'] = user.username
            
            flash('Registration successful! Welcome to Dealuxe!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
            return render_template('register.html', form=form)
    
    return render_template('register.html', form=form)


def register_api_internal():
    """Internal helper for API registration (JSON)"""
    data = request.json
    
    # Validate required fields
    required = ['username', 'email', 'password']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if username exists
    if get_user_by_username(data['username']):
        return jsonify({'error': 'Username already exists'}), 400
    
    # Check if email exists
    if get_user_by_email(data['email']):
        return jsonify({'error': 'Email already exists'}), 400
    
    try:
        # Create user and player
        user, player = create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            phone=data.get('phone'),
            full_name=data.get('full_name')
        )
        
        # Award welcome bonus (free cash)
        player.award_free_cash()
        
        # Log user in
        session['user_id'] = user.id
        session['username'] = user.username
        
        return jsonify({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            },
            'player': player.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login user (handles both form and API requests)"""
    # Check if this is a JSON API request
    if request.is_json:
        return login_api_internal()
    
    # Handle form submission
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Get user
        user = get_user_by_username(username)
        if not user or not user.check_password(password):
            flash('Invalid username or password', 'error')
            return render_template('login.html', form=form)
        
        if not user.is_active:
            flash('Account is disabled', 'error')
            return render_template('login.html', form=form)
        
        # Update last login
        user.update_last_login()
        
        # Set session
        session['user_id'] = user.id
        session['username'] = user.username
        
        flash('Login successful!', 'success')
        
        # Redirect to 'next' parameter or default to index
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('index'))
    
    return render_template('login.html', form=form)


def login_api_internal():
    """Internal helper for API login (JSON)"""
    data = request.json
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    # Get user
    user = get_user_by_username(data['username'])
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    
    if not user.is_active:
        return jsonify({'error': 'Account is disabled'}), 403
    
    # Update last login
    user.update_last_login()
    
    # Set session
    session['user_id'] = user.id
    session['username'] = user.username
    
    # Get player profile
    player = get_player_by_user_id(user.id)
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin
        },
        'player': player.to_dict() if player else None
    })


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Logout user (handles both form and API requests)"""
    session.clear()
    
    # If JSON request, return JSON response
    if request.is_json:
        return jsonify({'message': 'Logged out successfully'})
    
    # Otherwise redirect to login
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged in user"""
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    player = get_player_by_user_id(user.id)
    
    return jsonify({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'full_name': user.full_name,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None
        },
        'player': player.to_dict() if player else None
    })


@auth_bp.route('/player/balance', methods=['GET'])
@login_required
def get_balance():
    """Get player's current balance"""
    player = get_player_by_user_id(session['user_id'])
    if not player:
        return jsonify({'error': 'Player profile not found'}), 404
    
    return jsonify({
        'real_balance': player.real_balance,
        'fake_balance': player.fake_balance,
        'fake_balance_expires_at': player.fake_balance_expires_at.isoformat() if player.fake_balance_expires_at else None,
        'fake_cash_target': player.fake_cash_target,
        'is_fake_cash_valid': player.is_fake_cash_valid()
    })


@auth_bp.route('/player/stats', methods=['GET'])
@login_required
def get_stats():
    """Get player's game statistics"""
    player = get_player_by_user_id(session['user_id'])
    if not player:
        return jsonify({'error': 'Player profile not found'}), 404
    
    return jsonify({
        'total_games': player.total_games,
        'wins': player.wins,
        'losses': player.losses,
        'win_rate': player.get_win_rate(),
        'total_wagered': player.total_wagered,
        'total_winnings': player.total_winnings
    })


@auth_bp.route('/player/free-cash', methods=['POST'])
@login_required
def claim_free_cash():
    """Claim free cash (24hr bonus)"""
    player = get_player_by_user_id(session['user_id'])
    if not player:
        return jsonify({'error': 'Player profile not found'}), 404
    
    # Check if player already has valid free cash
    if player.is_fake_cash_valid():
        return jsonify({
            'error': 'You already have active free cash',
            'expires_at': player.fake_balance_expires_at.isoformat()
        }), 400
    
    # Award free cash
    player.award_free_cash()
    
    return jsonify({
        'message': 'Free cash awarded!',
        'fake_balance': player.fake_balance,
        'fake_cash_target': player.fake_cash_target,
        'expires_at': player.fake_balance_expires_at.isoformat()
    })


@auth_bp.route('/player/deposit', methods=['POST'])
@login_required
def deposit():
    """Deposit real money (placeholder - integrate payment gateway)"""
    data = request.json
    amount = data.get('amount', 0)
    
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    player = get_player_by_user_id(session['user_id'])
    if not player:
        return jsonify({'error': 'Player profile not found'}), 404
    
    # TODO: Integrate with payment gateway
    # For now, just add to balance (REMOVE IN PRODUCTION!)
    balance_before = player.real_balance
    player.real_balance += amount
    db.session.commit()
    
    # Log transaction
    from database import log_transaction
    log_transaction(
        player_id=player.id,
        transaction_type='deposit',
        amount=amount,
        balance_type='real',
        balance_before=balance_before,
        balance_after=player.real_balance,
        description='Real money deposit'
    )
    
    return jsonify({
        'message': 'Deposit successful',
        'new_balance': player.real_balance
    })


@auth_bp.route('/leaderboard', methods=['GET'])
def leaderboard():
    """Get leaderboard (top players)"""
    from database import Leaderboard
    
    limit = request.args.get('limit', 10, type=int)
    top_players = Leaderboard.get_top_players(limit=limit)
    
    result = []
    for rank, (player_id, username, total_games, wins, total_winnings, win_rate) in enumerate(top_players, 1):
        result.append({
            'rank': rank,
            'username': username,
            'total_games': total_games,
            'wins': wins,
            'total_winnings': total_winnings,
            'win_rate': round(win_rate, 2) if win_rate else 0.0
        })
    
    return jsonify({'leaderboard': result})


# ============================================================
# API-ONLY ROUTES (for backward compatibility with JSON clients)
# ============================================================

@auth_bp.route('/api/auth/register', methods=['POST'])
def register_api():
    """API endpoint for registration (JSON)"""
    data = request.json
    
    # Validate required fields
    required = ['username', 'email', 'password']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if username exists
    if get_user_by_username(data['username']):
        return jsonify({'error': 'Username already exists'}), 400
    
    # Check if email exists
    if get_user_by_email(data['email']):
        return jsonify({'error': 'Email already exists'}), 400
    
    try:
        # Create user and player
        user, player = create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            phone=data.get('phone'),
            full_name=data.get('full_name')
        )
        
        # Award welcome bonus (free cash)
        player.award_free_cash()
        
        # Log user in
        session['user_id'] = user.id
        session['username'] = user.username
        
        return jsonify({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            },
            'player': player.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
def login_api():
    """API endpoint for login (JSON)"""
    data = request.json
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    # Get user
    user = get_user_by_username(data['username'])
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    
    if not user.is_active:
        return jsonify({'error': 'Account is disabled'}), 403
    
    # Update last login
    user.update_last_login()
    
    # Set session
    session['user_id'] = user.id
    session['username'] = user.username
    
    # Get player profile
    player = get_player_by_user_id(user.id)
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin
        },
        'player': player.to_dict() if player else None
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout_api():
    """API endpoint for logout (JSON)"""
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


@auth_bp.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user_api():
    """API endpoint to get current logged in user (JSON)"""
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    player = get_player_by_user_id(user.id)
    
    return jsonify({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'full_name': user.full_name,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None
        },
        'player': player.to_dict() if player else None
    })
