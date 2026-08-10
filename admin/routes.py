from functools import wraps

from flask import Blueprint, jsonify, request, session

from admin.service import (
    cancel_tournament,
    dashboard_summary,
    list_tournaments,
    list_users,
    lock_tournament,
    start_tournament,
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
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403

        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    return jsonify(dashboard_summary())


@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    search = request.args.get('search', '').strip()
    return jsonify({'users': list_users(search)})


@admin_bp.route('/users/<int:user_id>', methods=['PATCH'])
@admin_required
def patch_user(user_id):
    data = request.get_json(silent=True) or {}
    try:
        user_payload = update_user(user_id, data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'User updated', 'user': user_payload})


@admin_bp.route('/tournaments', methods=['GET'])
@admin_required
def get_tournaments():
    return jsonify({'tournaments': list_tournaments()})


@admin_bp.route('/tournaments/<int:tournament_id>/lock', methods=['POST'])
@admin_required
def lock_tournament_route(tournament_id):
    return jsonify(lock_tournament(tournament_id))


@admin_bp.route('/tournaments/<int:tournament_id>/start', methods=['POST'])
@admin_required
def start_tournament_route(tournament_id):
    return jsonify(start_tournament(tournament_id))


@admin_bp.route('/tournaments/<int:tournament_id>/cancel', methods=['POST'])
@admin_required
def cancel_tournament_route(tournament_id):
    return jsonify(cancel_tournament(tournament_id))
