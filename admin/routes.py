from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session, render_template
from security.observability import read_security_audit

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
    user_activity,
    read_backend_logs,
    clear_backend_logs,
    create_cup_tournament,
    get_cup_placements,
    assign_cup_positions_5_to_8,
    assign_cup_positions_9_to_10,
    list_cup_replacement_candidates,
    replace_absent_cup_player,
    check_in_cup_qualification,
    list_cup_qualifications,
    move_cup_qualification_to_reserve,
    replace_cup_qualification,
    revoke_cup_qualification,
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


@admin_bp.route('/users/<int:user_id>/activity', methods=['GET'])
@admin_required
def user_activity_route(user_id):
    """Full activity for one user: profile + financial ledger + audit trail."""
    try:
        return jsonify(user_activity(user_id))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404


@admin_bp.route('/users/<int:user_id>/credits', methods=['POST'])
@admin_required
def award_user_credits(user_id):
    data = request.get_json(silent=True) or {}
    try:
        result = award_credits(
            session['user_id'], user_id,
            float(data.get('amount', 0)),
            data.get('balance_type', 'promotional'),
            data.get('reason', 'Promotional credits awarded'),
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


@admin_bp.route('/logs', methods=['GET'])
@admin_required
def backend_logs():
    """Tail of the backend print log (optional ?tail=N and ?search=...)."""
    try:
        tail = int(request.args.get('tail', 200))
    except (TypeError, ValueError):
        tail = 200
    search = (request.args.get('search') or '').strip() or None
    return jsonify(read_backend_logs(tail=tail, search=search))


@admin_bp.route('/logs/clear', methods=['POST'])
@admin_required
def clear_backend_logs_route():
    """Truncate the backend print log file."""
    return jsonify(clear_backend_logs())


@admin_bp.route('/security-events', methods=['GET'])
@admin_required
def security_events():
    """Return a bounded view of already-redacted structured security records."""
    try:
        tail = max(1, min(int(request.args.get('tail', 200)), 1000))
    except (TypeError, ValueError):
        tail = 200
    records = read_security_audit(
        current_app.config['SECURITY_AUDIT_FILE'],
        tail=tail,
        request_id=(request.args.get('request_id') or '').strip() or None,
        event=(request.args.get('event') or '').strip() or None,
        category=(request.args.get('category') or '').strip() or None,
        backup_count=current_app.config.get('SECURITY_AUDIT_BACKUP_COUNT', 7),
    )
    return jsonify({
        'events': records,
        'total': len(records),
        'mode': current_app.config.get('SECURITY_AUDIT_MODE', 'off'),
    })


@admin_bp.route('/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
    except (TypeError, ValueError):
        limit = 100
    return jsonify({'logs': list_audit_logs(limit)})


@admin_bp.route('/cup-qualifications', methods=['GET'])
@admin_required
def cup_qualification_roster():
    try:
        return jsonify(list_cup_qualifications(
            event_key=request.args.get('event_key'),
            status=request.args.get('status', '').strip(),
        ))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


@admin_bp.route('/cup-tournaments', methods=['POST'])
@admin_required
def create_cup_tournament_route():
    data = request.get_json(silent=True) or {}
    try:
        cup = create_cup_tournament(
            session['user_id'],
            tournament_name=data.get('tournament_name'),
            event_key=data.get('event_key'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': '64-player Cup created and started', 'cup': cup}), 201


@admin_bp.route('/cup-replacement-candidates', methods=['GET'])
@admin_required
def cup_replacement_candidates_route():
    return jsonify(list_cup_replacement_candidates(
        event_key=request.args.get('event_key')
    ))


@admin_bp.route(
    '/cup-qualifications/<int:qualification_id>/replace-absent', methods=['POST']
)
@admin_required
def cup_replace_absent_route(qualification_id):
    data = request.get_json(silent=True) or {}
    try:
        result = replace_absent_cup_player(
            qualification_id=qualification_id,
            candidate_user_id=data.get('candidate_user_id'),
            source_type=data.get('source_type'),
            source_tournament_id=data.get('source_tournament_id'),
            admin_user_id=session['user_id'],
            reason=data.get('reason'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Absent Cup player replaced', **result})


@admin_bp.route('/cup-tournaments/<int:tournament_id>/placements', methods=['GET'])
@admin_required
def cup_placements_route(tournament_id):
    try:
        return jsonify(get_cup_placements(tournament_id))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


@admin_bp.route(
    '/cup-tournaments/<int:tournament_id>/placements/5-8', methods=['PATCH']
)
@admin_required
def cup_positions_5_to_8_route(tournament_id):
    data = request.get_json(silent=True) or {}
    try:
        placements = assign_cup_positions_5_to_8(
            tournament_id,
            data.get('ordered_user_ids'),
            session['user_id'],
            data.get('reason'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Cup positions 5-8 saved', **placements})


@admin_bp.route(
    '/cup-tournaments/<int:tournament_id>/placements/9-10', methods=['PATCH']
)
@admin_required
def cup_positions_9_to_10_route(tournament_id):
    data = request.get_json(silent=True) or {}
    try:
        placements = assign_cup_positions_9_to_10(
            tournament_id,
            data.get('ordered_user_ids'),
            session['user_id'],
            data.get('reason'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Cup positions 9-10 saved', **placements})


@admin_bp.route('/cup-qualifications/<int:qualification_id>/check-in', methods=['POST'])
@admin_required
def cup_qualification_check_in(qualification_id):
    try:
        qualification = check_in_cup_qualification(
            qualification_id, session['user_id']
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Qualifier checked in', 'qualification': qualification})


@admin_bp.route('/cup-qualifications/<int:qualification_id>/reserve', methods=['POST'])
@admin_required
def cup_qualification_reserve(qualification_id):
    data = request.get_json(silent=True) or {}
    try:
        qualification = move_cup_qualification_to_reserve(
            qualification_id, session['user_id'], data.get('reason')
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Qualifier moved to reserve', 'qualification': qualification})


@admin_bp.route('/cup-qualifications/<int:qualification_id>/revoke', methods=['POST'])
@admin_required
def cup_qualification_revoke(qualification_id):
    data = request.get_json(silent=True) or {}
    try:
        qualification = revoke_cup_qualification(
            qualification_id, session['user_id'], data.get('reason')
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Qualification revoked', 'qualification': qualification})


@admin_bp.route('/cup-qualifications/<int:qualification_id>/replace', methods=['POST'])
@admin_required
def cup_qualification_replace(qualification_id):
    data = request.get_json(silent=True) or {}
    try:
        result = replace_cup_qualification(
            qualification_id,
            int(data.get('replacement_qualification_id')),
            session['user_id'],
            data.get('reason'),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Cup seat replaced', **result})


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
