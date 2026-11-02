"""
Authentication and User Management Routes
"""
import json

from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash, current_app
from database import (
    db, User, Player, create_user, 
    get_user_by_username, get_user_by_email,
    get_player_by_user_id, log_transaction, TX_PROMOTIONAL_CREDIT
)
from config import GameConfig
from Forms import LoginForm, RegistrationForm
from functools import wraps
from werkzeug.security import generate_password_hash
from datetime import datetime
from services.registration_verification import (
    RegistrationSetupError, create_challenge, find_challenge,
    verify_code_for_token,
)
from services.contact_validator import ContactValidator, ContactValidationError
from pricing.referrals import (
    attribute_referral,
    find_active_referral_code,
    get_or_create_referral_code,
    normalize_referral_code,
)
from security import (
    audit_security_event,
    current_request_id,
    establish_authenticated_session,
    machine_client_endpoint,
    safe_internal_error,
)

auth_bp = Blueprint('auth', __name__)


def _record_registration_setup_failure(exc, channel=None):
    """Record a searchable, non-sensitive cause for the support reference."""
    code = getattr(exc, 'code', 'registration_setup_failed')
    exception_type = type(exc.__cause__ or exc).__name__
    reference = current_request_id()
    current_app.logger.error(
        'Registration setup failed request_id=%s channel=%s failure_code=%s '
        'exception_type=%s provider_status=%s',
        reference or 'unavailable', channel or 'unknown', code, exception_type,
        getattr(exc, 'provider_status', None),
    )
    audit_security_event(
        'registration_failure', category='authentication', outcome='failed',
        status=500,
        details={
            'exception_type': exception_type,
            'failure_code': code,
            'channel': channel or 'unknown',
            'provider_status': getattr(exc, 'provider_status', None),
        },
    )


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
    referral_code=None, password_hash=None, commit=True,
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
        password_hash=password_hash,
    )
    _grant_registration_promotional_credits(player)
    get_or_create_referral_code(user.id, commit=False)
    if referral_code:
        attribute_referral(referral_code, user.id, commit=False)
    if commit:
        db.session.commit()
    return user, player


def _registration_pending_data(data):
    username = str(data.get('username') or '').strip()
    email = str(data.get('email') or '').strip().lower()
    password = str(data.get('password') or '')
    channel = str(data.get('verification_channel') or data.get('channel') or '').lower()
    if len(username) < 3 or len(username) > 20 or not email or len(password) < 6:
        raise ValueError('Enter a valid username, email and password (at least 6 characters).')
    if channel not in {'email', 'whatsapp'}:
        raise ValueError('Choose email or WhatsApp for your verification code.')
    if get_user_by_username(username):
        raise ValueError('Username already exists')
    if get_user_by_email(email):
        raise ValueError('Email already exists')
    _validate_optional_referral_code(data.get('referral_code'))
    phone = str(data.get('phone') or '').strip()
    if channel == 'whatsapp' and not phone:
        raise ValueError('Enter a phone number to receive a WhatsApp code.')
    country = data.get('country')
    if phone:
        phone = ContactValidator.normalize_phone(phone, country)
        if User.query.filter_by(phone=phone).first():
            raise ValueError(
                'This phone number is already linked to an account. Please sign in '
                'to that account or register with a different number.'
            )
    return {
        'username': username, 'email': email,
        'password_hash': generate_password_hash(password),
        'phone': phone or None, 'full_name': data.get('full_name') or data.get('name'),
        'country': country, 'referral_code': data.get('referral_code'),
    }, channel


def _finish_registration_verification(token, code):
    challenge = find_challenge(token)
    if not challenge:
        return None, 'Verification session was not found. Please register again.'
    valid, error = verify_code_for_token(challenge, token, code)
    if not valid:
        return None, error
    data = json.loads(challenge.pending_data)
    try:
        if get_user_by_username(data['username']) or get_user_by_email(data['email']):
            return None, 'An account with those details already exists. Please sign in.'
        if data.get('phone') and User.query.filter_by(phone=data['phone']).first():
            return None, (
                'This phone number is already linked to an account. Please sign in '
                'to that account or register with a different number.'
            )
        user, player = _complete_registration(
            username=data['username'], email=data['email'], password='',
            phone=data.get('phone'), full_name=data.get('full_name'),
            country=data.get('country'), referral_code=data.get('referral_code'),
            password_hash=data['password_hash'],
            commit=False,
        )
        challenge.consumed_at = datetime.now()
        db.session.commit()
        return (user, player), None
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            'Registration verification account creation failed request_id=%s exception_type=%s',
            current_request_id() or 'unavailable', type(exc).__name__,
        )
        audit_security_event(
            'registration_verification_failure', category='authentication',
            outcome='failed', status=500,
            details={'exception_type': type(exc).__name__},
        )
        raise


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
    if request.is_json:
        return register_api_internal()

    if request.method == 'POST' and request.form.get('verification_code'):
        token = session.get('registration_challenge')
        try:
            result, error = _finish_registration_verification(token, request.form.get('verification_code'))
            if error:
                challenge = find_challenge(token)
                remaining = max(0, int((challenge.expires_at - datetime.now()).total_seconds())) if challenge else 0
                flash(error, 'error')
                return render_template('register.html', form=RegistrationForm(), verification_pending=True, expires_in=remaining)
            user, _player = result
            session.pop('registration_challenge', None)
            establish_authenticated_session(user)
            flash('Your account is verified. Welcome to Dealuxe!', 'success')
            return redirect(url_for('index'))
        except Exception as exc:
            db.session.rollback()
            audit_security_event('registration_failure', category='authentication', outcome='failed', status=500,
                                 details={'exception_type': type(exc).__name__})
            flash('Verification could not be completed. Please try again.', 'error')
            challenge = find_challenge(token)
            remaining = max(0, int((challenge.expires_at - datetime.now()).total_seconds())) if challenge else 0
            return render_template('register.html', form=RegistrationForm(), verification_pending=True, expires_in=remaining)
    
    # Handle form submission
    form = RegistrationForm()
    
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        phone = form.phone.data
        full_name = form.name.data
        
        try:
            pending, channel = _registration_pending_data({
                'username': username, 'email': email, 'password': password,
                'phone': phone, 'full_name': full_name, 'country': form.country.data,
                'referral_code': form.referral_code.data,
                'verification_channel': request.form.get('verification_channel'),
            })
            token, challenge = create_challenge(
                channel=channel, recipient=email if channel == 'email' else phone,
                pending_data=pending,
            )
            session['registration_challenge'] = token
            flash('We sent a verification code. It expires in 5 minutes.', 'success')
            return render_template('register.html', form=RegistrationForm(), verification_pending=True,
                                   expires_in=max(0, int((challenge.expires_at - datetime.now()).total_seconds())))
        except ValueError as exc:
            flash(str(exc), 'error')
            return render_template('register.html', form=form)
            
        except Exception as exc:
            db.session.rollback()
            selected_channel = request.form.get('verification_channel')
            _record_registration_setup_failure(exc, selected_channel)
            reference = current_request_id()
            message = (
                exc.user_message if isinstance(exc, RegistrationSetupError) else
                'We could not start registration because of a temporary server issue. '
                'No account was created. Please try again later.'
            )
            if reference:
                message += f' Support reference: {reference}.'
            flash(message, 'error')
            return render_template('register.html', form=form)
    
    return render_template('register.html', form=form)


def register_api_internal():
    """Internal helper for API registration (JSON)"""
    data = request.json
    
    try:
        pending, channel = _registration_pending_data(data)
        token, challenge = create_challenge(
            channel=channel, recipient=pending['email'] if channel == 'email' else pending.get('phone'),
            pending_data=pending,
        )
        return jsonify({'message': 'Verification code sent', 'challenge_token': token,
                        'expires_in_seconds': max(0, int((challenge.expires_at - datetime.now()).total_seconds()))}), 202
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as exc:
        db.session.rollback()
        channel = str(data.get('verification_channel') or data.get('channel') or 'unknown')
        _record_registration_setup_failure(exc, channel)
        message = (
            exc.user_message if isinstance(exc, RegistrationSetupError) else
            'We could not start registration because of a temporary server issue. '
            'No account was created. Please try again later.'
        )
        return safe_internal_error(message, 'registration_failed')


@auth_bp.route('/api/auth/verify-registration', methods=['POST'])
@machine_client_endpoint
def verify_registration_api():
    data = request.get_json(silent=True) or {}
    token = data.get('challenge_token') or session.get('registration_challenge')
    try:
        result, error = _finish_registration_verification(token, data.get('code'))
        if error:
            return jsonify({'error': error}), 400
        user, player = result
        session.pop('registration_challenge', None)
        establish_authenticated_session(user)
        return jsonify({'message': 'Registration verified', 'user': {
            'id': user.id, 'username': user.username, 'email': user.email,
        }, 'player': player.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return safe_internal_error('Verification could not be completed', 'registration_verification_failed')


def _password_reset_user(email):
    """Find an account by email; usernames are public game-display names."""
    email = str(email or '').strip().lower()
    if not email:
        return None
    return get_user_by_email(email)


def _masked_phone_hint(phone):
    digits = ''.join(character for character in str(phone or '') if character.isdigit())
    return f'ending in {digits[-1]}' if digits else 'on this account'


def _recovery_phone_matches(user, supplied_phone):
    """Validate the supplied contact and compare it safely to legacy values."""
    normalized = ContactValidator.normalize_phone(supplied_phone, user.country)
    stored_digits = ''.join(character for character in str(user.phone or '') if character.isdigit())
    supplied_digits = normalized[1:]
    if not stored_digits:
        return False, normalized
    # Prefer exact E.164 comparison. The suffix case supports accounts created
    # before phone numbers were normalized and stored only the national number.
    matches = (
        stored_digits == supplied_digits
        or supplied_digits.endswith(stored_digits.lstrip('0'))
        or stored_digits.endswith(supplied_digits.lstrip('0'))
    )
    return matches, normalized


def _password_reset_remaining(token):
    challenge = find_challenge(token, purpose='password_reset')
    if not challenge:
        return 0
    return max(0, int((challenge.expires_at - datetime.now()).total_seconds()))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Send and verify a WhatsApp password-recovery code."""
    token = session.get('password_reset_challenge')

    # Preserve a valid code-entry step across a refresh or an unrelated render
    # error. The code itself remains the authority; this merely restores the UI.
    if request.method == 'GET' and token:
        remaining = _password_reset_remaining(token)
        if remaining:
            return render_template('forgot_password.html', verification_pending=True,
                                   expires_in=remaining)
        session.pop('password_reset_challenge', None)

    if request.method == 'POST' and request.form.get('verification_code'):
        new_password = str(request.form.get('new_password') or '')
        confirm_password = str(request.form.get('confirm_password') or '')
        if len(new_password) < 6:
            flash('Your new password must be at least 6 characters.', 'error')
            return render_template('forgot_password.html', verification_pending=True,
                                   expires_in=_password_reset_remaining(token))
        if new_password != confirm_password:
            flash('The new-password entries do not match.', 'error')
            return render_template('forgot_password.html', verification_pending=True,
                                   expires_in=_password_reset_remaining(token))

        challenge = find_challenge(token, purpose='password_reset')
        if not challenge:
            flash('Your recovery session was not found or has expired. Please request a new code.', 'error')
            session.pop('password_reset_challenge', None)
            return render_template('forgot_password.html')
        valid, error = verify_code_for_token(challenge, token, request.form.get('verification_code'))
        if not valid:
            flash(error, 'error')
            return render_template('forgot_password.html', verification_pending=True,
                                   expires_in=_password_reset_remaining(token))
        try:
            data = json.loads(challenge.pending_data)
            user = db.session.get(User, data.get('user_id'))
            if not user or not user.is_active:
                flash('This recovery request is no longer valid. Please contact support.', 'error')
                return render_template('forgot_password.html')
            user.set_password(new_password)
            challenge.consumed_at = datetime.now()
            db.session.commit()
            session.pop('password_reset_challenge', None)
            audit_security_event(
                'password_reset_completed', category='authentication', outcome='success', status=200,
            )
            flash('Your password has been changed. Please sign in with your new password.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(
                'Password reset failed request_id=%s exception_type=%s',
                current_request_id() or 'unavailable', type(exc).__name__,
            )
            audit_security_event(
                'password_reset_failed', category='authentication', outcome='failed', status=500,
                details={'exception_type': type(exc).__name__},
            )
            flash('Your password could not be changed due to a temporary server issue. Please try again.', 'error')
            return render_template('forgot_password.html', verification_pending=True,
                                   expires_in=_password_reset_remaining(token))

    if request.method == 'POST' and request.form.get('confirm_phone'):
        candidate_user_id = session.get('password_reset_candidate_user_id')
        user = db.session.get(User, candidate_user_id) if candidate_user_id else None
        if not user or not user.is_active or not user.phone:
            session.pop('password_reset_candidate_user_id', None)
            flash('Your recovery request has expired. Please start again.', 'error')
            return render_template('forgot_password.html')
        try:
            phone_matches, verified_phone = _recovery_phone_matches(
                user, request.form.get('phone')
            )
        except ContactValidationError as exc:
            flash(str(exc), 'error')
            return render_template(
                'forgot_password.html', phone_confirmation=True,
                phone_hint=_masked_phone_hint(user.phone),
            )
        if not phone_matches:
            flash('The email address and phone number do not match our records.', 'error')
            return render_template(
                'forgot_password.html', phone_confirmation=True,
                phone_hint=_masked_phone_hint(user.phone),
            )
        try:
            token, challenge = create_challenge(
                channel='whatsapp', recipient=verified_phone,
                pending_data={'user_id': user.id, 'phone': verified_phone},
                purpose='password_reset',
            )
            session['password_reset_challenge'] = token
            session.pop('password_reset_candidate_user_id', None)
            flash('We sent a recovery code to your WhatsApp. It expires in 5 minutes.', 'success')
            return render_template(
                'forgot_password.html', verification_pending=True,
                expires_in=max(0, int((challenge.expires_at - datetime.now()).total_seconds())),
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(
                'Password reset setup failed request_id=%s channel=whatsapp failure_code=%s exception_type=%s provider_status=%s',
                current_request_id() or 'unavailable',
                getattr(exc, 'code', 'password_reset_setup_failed'),
                type(exc.__cause__ or exc).__name__, getattr(exc, 'provider_status', None),
            )
            audit_security_event(
                'password_reset_delivery_failure', category='authentication', outcome='failed', status=500,
                details={
                    'exception_type': type(exc.__cause__ or exc).__name__,
                    'failure_code': getattr(exc, 'code', 'password_reset_setup_failed'),
                    'channel': 'whatsapp',
                    'provider_status': getattr(exc, 'provider_status', None),
                },
            )
            message = (
                exc.user_message if isinstance(exc, RegistrationSetupError) else
                'We could not send the recovery code because of a temporary server issue. Please try again.'
            )
            flash(message, 'error')
            active_token = session.get('password_reset_challenge')
            if active_token and _password_reset_remaining(active_token):
                return render_template(
                    'forgot_password.html', verification_pending=True,
                    expires_in=_password_reset_remaining(active_token),
                )
            return render_template(
                'forgot_password.html', phone_confirmation=True,
                phone_hint=_masked_phone_hint(user.phone),
            )

    if request.method == 'POST':
        user = _password_reset_user(request.form.get('email'))
        session.pop('password_reset_candidate_user_id', None)
        # Do not send a code until the player has also proved knowledge of the
        # registered phone number. Usernames are intentionally not accepted.
        if not user or not user.is_active or not user.phone:
            flash('If an active account matches that email address, continue with the requested recovery details.', 'info')
            return render_template('forgot_password.html')
        session['password_reset_candidate_user_id'] = user.id
        return render_template(
            'forgot_password.html', phone_confirmation=True,
            phone_hint=_masked_phone_hint(user.phone),
        )

    return render_template('forgot_password.html')


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
        establish_authenticated_session(user)
        
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
    establish_authenticated_session(user)
    
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


@auth_bp.route('/logout', methods=['POST'])
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
    """API endpoint starts, but does not complete, registration."""
    data = request.json or {}
    try:
        pending, channel = _registration_pending_data(data)
        token, challenge = create_challenge(channel=channel,
                    recipient=pending['email'] if channel == 'email' else pending.get('phone'),
                    pending_data=pending)
        return jsonify({'message': 'Verification code sent', 'challenge_token': token,
                        'expires_in_seconds': max(0, int((challenge.expires_at - datetime.now()).total_seconds()))}), 202
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.session.rollback()
        return safe_internal_error(
            'Registration could not be completed', 'registration_failed'
        )


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
    establish_authenticated_session(user)
    
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
