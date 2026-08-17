from functools import wraps

from flask import Blueprint, jsonify, request, session, render_template

from admin.service import (
    adjust_wallet,
    award_credits,
    cancel_tournament,
    complete_tournament,
    create_dispute,
    create_test_tournament,
    dashboard_summary,
    force_start,
    get_tournament_detail,
    list_audit_logs,
    list_disputes,
    list_tournaments,
    list_users,
    lock_tournament,
    resolve_dispute,
    start_tournament,
    test_bots_enabled,
    update_user,
)
from database import User

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin', template_folder='templates')


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        user = User.query.get(user_id)
        if not user or not (user.is_admin or user.is_super_admin):
            return jsonify({'error': 'Admin privileges required'}), 403

        return f(*args, **kwargs)

    return decorated_function


def login_required_only(f):
    """Requires authentication but not admin rights (e.g. players filing a dispute)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    return jsonify(dashboard_summary())

@admin_bp.route('/admin', methods=['GET'])
@admin_required
def admin():
    return render_template("admin.html")


@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    search = request.args.get('search', '').strip()
    return jsonify({'users': list_users(search)})


@admin_bp.route('/users/<int:user_id>', methods=['PATCH'])
@admin_required
def patch_user(user_id):
    data = request.get_json(silent=True) or {}
    if 'is_admin' in data or 'is_super_admin' in data:
        return jsonify({
            'error': 'Admin roles are managed via the super admin CLI only '
                     '(python super_admin_cli.py assign/revoke).'
        }), 400
    try:
        user_payload = update_user(user_id, data, admin_user_id=session['user_id'])
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'User updated', 'user': user_payload})


@admin_bp.route('/users/<int:user_id>/credits', methods=['POST'])
@admin_required
def award_user_credits(user_id):
    data = request.get_json(silent=True) or {}
    try:
        result = award_credits(
            session['user_id'], user_id,
            float(data.get('amount', 0)),
            data.get('balance_type', 'fake'),
            data.get('reason', 'Free credits awarded'),
        )
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Credits awarded', 'wallet': result})


@admin_bp.route('/wallets/<int:user_id>/adjust', methods=['POST'])
@admin_required
def adjust_wallet_route(user_id):
    data = request.get_json(silent=True) or {}
    try:
        result = adjust_wallet(
            session['user_id'], user_id,
            data.get('balance_type', 'real'),
            data.get('delta', 0),
            data.get('reason'),
        )
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Wallet adjusted', 'wallet': result})


@admin_bp.route('/tournaments', methods=['GET'])
@admin_required
def get_tournaments():
    return jsonify({'tournaments': list_tournaments()})


@admin_bp.route('/tournaments/<int:tournament_id>', methods=['GET'])
@admin_required
def tournament_detail_route(tournament_id):
    return jsonify(get_tournament_detail(tournament_id))


@admin_bp.route('/tournaments/<int:tournament_id>/lock', methods=['POST'])
@admin_required
def lock_tournament_route(tournament_id):
    return jsonify(lock_tournament(tournament_id, session['user_id']))


@admin_bp.route('/tournaments/<int:tournament_id>/start', methods=['POST'])
@admin_required
def start_tournament_route(tournament_id):
    return jsonify(start_tournament(tournament_id, session['user_id']))


@admin_bp.route('/tournaments/<int:tournament_id>/force-start', methods=['POST'])
@admin_required
def force_start_route(tournament_id):
    try:
        return jsonify(force_start(tournament_id, session['user_id']))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


@admin_bp.route('/tournaments/<int:tournament_id>/complete', methods=['POST'])
@admin_required
def complete_tournament_route(tournament_id):
    return jsonify(complete_tournament(tournament_id, session['user_id']))


@admin_bp.route('/tournaments/<int:tournament_id>/cancel', methods=['POST'])
@admin_required
def cancel_tournament_route(tournament_id):
    return jsonify(cancel_tournament(tournament_id, session['user_id']))


@admin_bp.route('/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
    except (TypeError, ValueError):
        limit = 100
    return jsonify({'logs': list_audit_logs(limit)})


@admin_bp.route('/disputes', methods=['GET'])
@admin_required
def get_disputes():
    status = request.args.get('status', '').strip()
    return jsonify({'disputes': list_disputes(status)})


@admin_bp.route('/disputes', methods=['POST'])
@login_required_only
def file_dispute():
    """Players file a dispute (login required, not admin-only)."""
    data = request.get_json(silent=True) or {}
    try:
        dispute = create_dispute(session['user_id'], data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Dispute filed', 'dispute': dispute}), 201


@admin_bp.route('/disputes/<int:dispute_id>/resolve', methods=['POST'])
@admin_required
def resolve_dispute_route(dispute_id):
    data = request.get_json(silent=True) or {}
    try:
        dispute = resolve_dispute(
            dispute_id, session['user_id'],
            data.get('status', 'resolved'),
            data.get('resolution'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Dispute updated', 'dispute': dispute})


@admin_bp.route('/test-tournament/status', methods=['GET'])
@admin_required
def test_tournament_status_route():
    """Whether the reserved tournament_bot_* accounts will auto-play."""
    enabled = test_bots_enabled()
    return jsonify({
        'bots_enabled': enabled,
        'message': (
            'Bots are enabled — tournament_bot_* accounts play their turns automatically.'
            if enabled
            else 'Bots are DISABLED. Restart the app with TOURNAMENT_TEST_BOTS_ENABLED=true '
                  'or matches will stall on the bot turn.'
        ),
    })


@admin_bp.route('/test-tournament', methods=['POST'])
@admin_required
def create_test_tournament_route():
    """Create a local test tournament: one manual player + three bots."""
    data = request.get_json(silent=True) or {}
    manual_username = (data.get('manual_username') or 'tournament_tester').strip()
    try:
        result = create_test_tournament(session['user_id'], manual_username)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Test tournament created', 'test': result}), 201
