"""Owner/admin-only routes for the disabled-by-default Hybrid foundation."""

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, send_from_directory, session, url_for

from controllers.auth_controller import admin_required, login_required
from admin.service import log_admin_action
from database import GameRoom, User, db
from hybrid.service import (
    block_user,
    create_report,
    get_game_context,
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
    update_game_profile_visibility,
)
from hybrid.shadow import list_match_audits, shadow_mode_enabled
from hybrid.settings import EDITABLE_FLAGS, serialize_settings, update_settings
from hybrid.metrics import pilot_metrics_snapshot
from hybrid.bracket_discovery import open_bracket_relevance
from hybrid.catalog import (
    ALLOWED_PLACEHOLDERS,
    CATEGORIES,
    INTENTS,
    create_caption_template,
    list_caption_templates,
    update_caption_template,
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


@hybrid_bp.get('/api/hybrid/open-brackets/relevance')
@login_required
def open_bracket_relevance_api():
    results = open_bracket_relevance(session['user_id'], current_app.config)
    if results is None:
        abort(404)
    return jsonify({'brackets': results})


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


@hybrid_bp.route('/api/hybrid/game/<room_code>/context', methods=['GET'])
@login_required
def game_context_api(room_code):
    """Private opponent context for the requesting game-room participant only."""
    _require_enabled()
    user = _current_user()
    try:
        context = get_game_context(user.id, room_code)
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except Exception:
        current_app.logger.exception(
            'Optional Q-messanger context failed for room %s', room_code
        )
        return jsonify({
            'error': 'Q-messanger profile context is temporarily unavailable',
        }), 503
    return jsonify({'context': context})


@hybrid_bp.route('/api/hybrid/game/<room_code>/preferences', methods=['PUT'])
@login_required
def game_preferences_api(room_code):
    """Update only the requesting participant's per-game profile sharing."""
    _require_enabled()
    user = _current_user()
    payload = _json_object()
    if set(payload) != {'profile_visible'}:
        return jsonify({'error': 'profile_visible is required'}), 400
    try:
        visible = update_game_profile_visibility(
            user.id, room_code, payload['profile_visible']
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Optional Q-messanger preference update failed for room %s', room_code
        )
        return jsonify({
            'error': 'Q-messanger profile preference is temporarily unavailable',
        }), 503
    room = GameRoom.query.filter_by(room_code=room_code).first()
    opponent_id = room.get_opponent_id(user.id) if room else None
    socketio = current_app.extensions.get('socketio')
    if socketio is not None and opponent_id is not None:
        try:
            socketio.emit(
                'hybrid_profile_visibility_changed',
                {'room_code': room_code},
                room='user_{0}'.format(opponent_id),
            )
        except Exception:
            # The periodic requester refresh remains the safe fallback.
            current_app.logger.exception(
                'Could not publish profile visibility refresh for room %s',
                room_code,
            )
    return jsonify({
        'message': 'Per-game profile preference updated',
        'profile_visible': visible,
    })


@hybrid_bp.route('/api/hybrid/game/<room_code>/opponent-image', methods=['GET'])
@login_required
def game_opponent_image(room_code):
    """Serve a visible opponent's dedicated profile image to one room member."""
    _require_enabled()
    user = _current_user()
    try:
        context = get_game_context(user.id, room_code)
    except LookupError:
        abort(404)
    except PermissionError:
        abort(403)
    if not context.get('available'):
        abort(404)

    from database import GameRoom
    from user.service import upload_dir

    room = GameRoom.query.filter_by(room_code=room_code).first()
    opponent_id = room.get_opponent_id(user.id) if room else None
    opponent = db.session.get(User, opponent_id) if opponent_id else None
    relative_path = opponent.profile_image_path if opponent else None
    if not relative_path:
        abort(404)
    owner_id, separator, filename = relative_path.partition('/')
    if not separator or owner_id != str(opponent_id) or not filename:
        abort(404)
    return send_from_directory(upload_dir(opponent_id), filename)


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


@hybrid_bp.route('/api/admin/hybrid/match-audits', methods=['GET'])
@admin_required
def admin_match_audits_api():
    _require_enabled()
    live_mode = bool(
        current_app.config.get('HYBRID_ENABLED', False)
        and current_app.config.get('HYBRID_PROFILE_ENABLED', False)
        and current_app.config.get('HYBRID_MATCHING_ENABLED', False)
    )
    if not shadow_mode_enabled(current_app.config) and not live_mode:
        abort(404)
    try:
        audits = list_match_audits(request.args.get('limit', 100))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'audits': audits, 'mode': 'live' if live_mode else 'shadow'})


@hybrid_bp.route('/api/admin/hybrid/pilot-metrics', methods=['GET'])
@admin_required
def admin_hybrid_pilot_metrics_api():
    """Aggregate pilot health only; available even while Hybrid is switched off."""
    return jsonify({'metrics': pilot_metrics_snapshot()})


@hybrid_bp.route('/api/admin/hybrid/settings', methods=['GET', 'PATCH'])
@admin_required
def admin_hybrid_settings_api():
    if request.method == 'GET':
        return jsonify({'settings': serialize_settings(current_app.config)})
    previous = {
        key: bool(current_app.config.get(key, False)) for key in EDITABLE_FLAGS
    }
    try:
        payload = _json_object()
        settings = update_settings(payload, session['user_id'], current_app.config)
        effective = {
            item['key']: item['enabled'] for item in settings['editable']
        }
        log_admin_action(
            session['user_id'],
            'hybrid_feature_settings_updated',
            entity_type='hybrid_settings',
            summary='Hybrid MVP feature settings updated',
            details=', '.join(
                f'{key}={str(value).lower()}'
                for key, value in effective.items()
            ),
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        current_app.config.update(previous)
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.config.update(previous)
        return jsonify({'error': 'Could not save Hybrid settings'}), 500
    return jsonify({
        'message': 'Hybrid settings saved',
        'settings': serialize_settings(current_app.config),
    })


@hybrid_bp.route('/api/admin/hybrid/captions', methods=['GET', 'POST'])
@admin_required
def admin_caption_catalogue_api():
    if request.method == 'GET':
        return jsonify({
            'captions': list_caption_templates(),
            'intents': INTENTS,
            'categories': CATEGORIES,
            'allowed_placeholders': sorted(ALLOWED_PLACEHOLDERS),
        })
    try:
        caption = create_caption_template(_json_object(), session['user_id'])
        log_admin_action(
            session['user_id'],
            'hybrid_caption_template_created',
            entity_type='discovery_caption_template',
            entity_id=caption['id'],
            summary=f"Caption template {caption['code']} created",
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Caption template created', 'caption': caption}), 201


@hybrid_bp.route('/api/admin/hybrid/captions/<int:template_id>', methods=['PATCH'])
@admin_required
def admin_caption_template_api(template_id):
    try:
        caption = update_caption_template(
            template_id, _json_object(), session['user_id']
        )
        log_admin_action(
            session['user_id'],
            'hybrid_caption_template_updated',
            entity_type='discovery_caption_template',
            entity_id=template_id,
            summary=f"Caption template {caption['code']} updated",
            details=f"active={str(caption['is_active']).lower()}",
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 404
    return jsonify({'message': 'Caption template updated', 'caption': caption})
