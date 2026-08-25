"""Owner/admin-only routes for the disabled-by-default Hybrid foundation."""

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, session, url_for

from controllers.auth_controller import admin_required, login_required
from admin.service import log_admin_action
from database import User, db
from hybrid.service import (
    block_user,
    create_report,
    get_profile_payload,
    hybrid_profile_enabled,
    list_blocks,
    list_profiles,
    list_reports,
    list_own_reports,
    moderate_profile,
    profile_options,
    review_report,
    unblock_user,
    update_profile,
)


hybrid_bp = Blueprint('hybrid', __name__)


def _require_enabled():
    if not hybrid_profile_enabled(current_app.config):
        abort(404)


def _current_user():
    user = db.session.get(User, session.get('user_id'))
    if user is None:
        abort(401)
    return user


def _json_object():
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError('JSON payload must be an object')
    return payload


@hybrid_bp.route('/api/hybrid/profile', methods=['GET', 'PATCH'])
@login_required
def own_profile_api():
    _require_enabled()
    user = _current_user()
    if request.method == 'GET':
        return jsonify({
            'profile': get_profile_payload(user),
            'options': profile_options(),
        })
    try:
        profile = update_profile(user, _json_object())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Discovery profile updated', 'profile': profile})


@hybrid_bp.route('/account/discovery', methods=['POST'])
@login_required
def account_profile_update():
    _require_enabled()
    user = _current_user()
    payload = {
        field: request.form.get(field)
        for field in (
            'intent', 'category', 'subcategory', 'location',
            'predefined_caption', 'custom_caption',
        )
    }
    for checkbox in ('is_enabled', 'is_visible', 'chat_preference_enabled'):
        payload[checkbox] = checkbox in request.form
    try:
        update_profile(user, payload)
    except ValueError as exc:
        flash(str(exc), 'error')
    else:
        flash('Discovery profile updated', 'success')
    return redirect(url_for('user.account_page'))


@hybrid_bp.route('/api/admin/hybrid/profiles', methods=['GET'])
@admin_required
def admin_profiles_api():
    _require_enabled()
    return jsonify({'profiles': list_profiles(), 'options': profile_options()})


@hybrid_bp.route('/api/admin/hybrid/profiles/<int:profile_id>/moderation', methods=['PATCH'])
@admin_required
def admin_profile_moderation_api(profile_id):
    _require_enabled()
    try:
        payload = _json_object()
        profile = moderate_profile(
            profile_id,
            session['user_id'],
            payload.get('decision'),
            payload.get('note'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    log_admin_action(
        session['user_id'],
        'hybrid_caption_moderated',
        entity_type='discovery_profile',
        entity_id=profile_id,
        summary=f"Custom caption {profile['moderation_status']}",
        details=profile.get('moderation_note'),
    )
    db.session.commit()
    return jsonify({'message': 'Caption moderation updated', 'profile': profile})


@hybrid_bp.route('/api/hybrid/blocks', methods=['GET', 'POST'])
@login_required
def own_blocks_api():
    _require_enabled()
    user = _current_user()
    if request.method == 'GET':
        return jsonify({'blocks': list_blocks(user.id)})
    try:
        payload = _json_object()
        block = block_user(user.id, payload.get('blocked_user_id'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'message': 'User blocked', 'block': block}), 201


@hybrid_bp.route('/api/hybrid/blocks/<int:blocked_user_id>', methods=['DELETE'])
@login_required
def own_block_delete_api(blocked_user_id):
    _require_enabled()
    user = _current_user()
    try:
        unblock_user(user.id, blocked_user_id)
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'message': 'User unblocked'})


@hybrid_bp.route('/account/discovery/block', methods=['POST'])
@login_required
def account_block_user():
    _require_enabled()
    user = _current_user()
    username = str(request.form.get('username') or '').strip()
    target = User.query.filter_by(username=username).first()
    if target is None:
        flash('Player not found', 'error')
    else:
        try:
            block_user(user.id, target.id)
        except ValueError as exc:
            flash(str(exc), 'error')
        else:
            flash('Player blocked from future Hybrid interactions', 'success')
    return redirect(url_for('user.account_page'))


@hybrid_bp.route('/account/discovery/unblock', methods=['POST'])
@login_required
def account_unblock_user():
    _require_enabled()
    user = _current_user()
    try:
        blocked_user_id = int(request.form.get('blocked_user_id'))
        unblock_user(user.id, blocked_user_id)
    except (TypeError, ValueError, LookupError) as exc:
        flash(str(exc) or 'Invalid block', 'error')
    else:
        flash('Player unblocked', 'success')
    return redirect(url_for('user.account_page'))


@hybrid_bp.route('/api/hybrid/reports', methods=['GET', 'POST'])
@login_required
def own_reports_api():
    _require_enabled()
    user = _current_user()
    if request.method == 'GET':
        return jsonify({'reports': list_own_reports(user.id)})
    try:
        report = create_report(user.id, _json_object())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'message': 'Report submitted', 'report': report}), 201


@hybrid_bp.route('/account/discovery/report', methods=['POST'])
@login_required
def account_report_user():
    _require_enabled()
    user = _current_user()
    username = str(request.form.get('username') or '').strip()
    target = User.query.filter_by(username=username).first()
    if target is None:
        flash('Player not found', 'error')
    else:
        try:
            create_report(user.id, {
                'reported_user_id': target.id,
                'reason_code': request.form.get('reason_code'),
                'details': request.form.get('details'),
            })
        except (ValueError, LookupError) as exc:
            flash(str(exc), 'error')
        else:
            flash('Safety report submitted privately', 'success')
    return redirect(url_for('user.account_page'))


@hybrid_bp.route('/api/admin/hybrid/reports', methods=['GET'])
@admin_required
def admin_reports_api():
    _require_enabled()
    try:
        reports = list_reports(request.args.get('status') or None)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'reports': reports, 'statuses': ('pending', 'in_review', 'resolved', 'rejected')})


@hybrid_bp.route('/api/admin/hybrid/reports/<int:report_id>', methods=['PATCH'])
@admin_required
def admin_report_review_api(report_id):
    _require_enabled()
    try:
        payload = _json_object()
        report = review_report(
            report_id,
            session['user_id'],
            payload.get('status'),
            payload.get('resolution'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    log_admin_action(
        session['user_id'],
        'hybrid_report_reviewed',
        entity_type='discovery_report',
        entity_id=report_id,
        summary=f"Discovery report marked {report['status']}",
        details=report.get('resolution'),
    )
    db.session.commit()
    return jsonify({'message': 'Report review updated', 'report': report})
