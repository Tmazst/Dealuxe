"""
Authentication and User Management Routes
"""
from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database import (
    db, User, Player, create_user, 
    get_user_by_username, get_user_by_email,
    get_player_by_user_id, log_transaction, TX_PROMOTIONAL_CREDIT
)
from config import GameConfig
from Forms import LoginForm, RegistrationForm
from functools import wraps
from pricing.referrals import (
    attribute_referral,
    find_active_referral_code,
    get_or_create_referral_code,
    normalize_referral_code,
)
from security import machine_client_endpoint

auth_bp = Blueprint('auth', __name__)


def _grant_registration_promotional_credits(player):
    """Grant and audit the approved one-time registration credit."""
    balance_before = float(player.promotional_credit_balance or 0.0)
    amount = GameConfig.get_registration_promotional_credit()
    player.grant_registration_promotional_credits(commit=False)
    log_transaction(
        player_id=player.id,
        transaction_type=TX_PROMOTIONAL_CREDIT,
        amount=amount,
        balance_type='promotional',
        balance_before=balance_before,
        balance_after=player.promotional_credit_balance,
        description='Version 3 registration promotional credit',
        commit=False,
    )


def _validate_optional_referral_code(value):
    code = normalize_referral_code(value)
    if not code:
        return None
    if find_active_referral_code(code) is None:
        raise ValueError('Referral code is invalid or inactive')
    return code


def _complete_registration(
    *, username, email, password, phone=None, full_name=None, country=None,
    referral_code=None,
):
    """Create the account, wallet grant, own code and attribution atomically."""
    referral_code = _validate_optional_referral_code(referral_code)
    user, player = create_user(
        username=username,
        email=email,
        password=password,
        phone=phone,
        full_name=full_name,
        country=country,
        commit=False,
    )
    _grant_registration_promotional_credits(player)
    get_or_create_referral_code(user.id, commit=False)
    if referral_code:
        attribute_referral(referral_code, user.id, commit=False)
    db.session.commit()
    return user, player


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin (or super admin) privileges for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user = User.query.get(session['user_id'])
        if not user or not (user.is_admin or user.is_super_admin):
            return jsonify({'error': 'Admin privileges required'}), 403

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
            user, player = _complete_registration(
                username=username,
                email=email,
                password=password,
                phone=phone,
                full_name=full_name,
                country=form.country.data,
                referral_code=form.referral_code.data,
            )
            
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
        user, player = _complete_registration(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            phone=data.get('phone'),
            full_name=data.get('full_name'),
            country=data.get('country'),
            referral_code=data.get('referral_code'),
        )
        
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
        
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
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
        next_page = request.form.get('next') or request.args.get('next')
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
            'country': user.country,
            'address': user.address,
            'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
            'id_number': user.id_number,
            'kyc_status': user.kyc_status or 'not_submitted',
            'kyc_document_path': user.kyc_document_path,
            'id_photo_path': user.id_photo_path,
            'id_photo_back_path': user.id_photo_back_path,
            'is_admin': user.is_admin,
            'is_super_admin': user.is_super_admin,
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
        'promotional_credit_balance': player.promotional_credit_balance,
        'promotional_credit_expires_at': player.promotional_credit_expires_at.isoformat() if player.promotional_credit_expires_at else None,
        'has_active_promotional_credits': player.has_active_promotional_credits(),
        # Legacy client aliases.
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
    """Deprecated endpoint; registered credits are granted by approved flows."""
    player = get_player_by_user_id(session['user_id'])
    if not player:
        return jsonify({'error': 'Player profile not found'}), 404
    
    return jsonify({
        'error': 'Self-service credit claims are disabled. Promotional credits are granted through registration, referrals or administrators.',
        'promotional_credit_balance': player.promotional_credit_balance,
        'promotional_credit_expires_at': player.promotional_credit_expires_at.isoformat() if player.promotional_credit_expires_at else None,
    }), 409


@auth_bp.route('/player/deposit', methods=['POST'])
@login_required
def deposit():
    """Deposit / top up the wallet.

    Gateway-aware: mock/sandbox mode credits locally (development); real mode
    initiates a MojaPOS payment and the wallet is credited only via the gateway
    callback. This never credits real balance without payment when the real
    gateway is enabled.
    """
    data = request.json or {}
    amount = data.get('amount', 0)

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    from user.service import initiate_topup
    result = initiate_topup(user, amount)
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Deposit failed')}), 400

    response = {'message': 'Deposit initiated successfully'}
    response.update(result)
    return jsonify(response)


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
@machine_client_endpoint
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
        user, player = _complete_registration(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            phone=data.get('phone'),
            full_name=data.get('full_name'),
            country=data.get('country'),
            referral_code=data.get('referral_code'),
        )
        
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
        
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
@machine_client_endpoint
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
@machine_client_endpoint
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
            'country': user.country,
            'address': user.address,
            'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
            'id_number': user.id_number,
            'kyc_status': user.kyc_status or 'not_submitted',
            'kyc_document_path': user.kyc_document_path,
            'id_photo_path': user.id_photo_path,
            'id_photo_back_path': user.id_photo_back_path,
            'is_admin': user.is_admin,
            'is_super_admin': user.is_super_admin,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None
        },
        'player': player.to_dict() if player else None
    })
