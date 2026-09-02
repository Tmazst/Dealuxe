"""Pricing catalogue, purchases, entitlements and administrator switches."""

from flask import Blueprint, current_app, jsonify, request, session

from admin.service import log_admin_action
from controllers.auth_controller import admin_required, login_required
from database import PlanPurchase, User, db
from .catalog import serialize_catalog
from .service import (
    entitlement_payload,
    initiate_plan_purchase,
    purchase_payload,
)
from .settings import (
    EDITABLE_PRICING_FLAGS,
    serialize_pricing_settings,
    update_pricing_settings,
)


pricing_bp = Blueprint('pricing', __name__)


@pricing_bp.get('/api/pricing/plans')
def pricing_plans_api():
    return jsonify(serialize_catalog(current_app.config))


@pricing_bp.route('/api/pricing/me', methods=['GET'])
@login_required
def my_pricing_api():
    user_id = session['user_id']
    purchases = PlanPurchase.query.filter_by(user_id=user_id).order_by(
        PlanPurchase.created_at.desc()
    ).limit(20).all()
    return jsonify({
        'entitlement': entitlement_payload(user_id),
        'purchases': [purchase_payload(row) for row in purchases],
    })


@pricing_bp.route('/api/pricing/purchases', methods=['POST'])
@login_required
def purchase_plan_api():
    user = db.session.get(User, session['user_id'])
    payload = request.get_json(silent=True) or {}
    try:
        purchase = initiate_plan_purchase(user, payload.get('plan_code'))
    except (ValueError, LookupError) as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except RuntimeError:
        db.session.rollback()
        return jsonify({'error': 'Plan payment could not be initiated'}), 503
    return jsonify({
        'message': (
            'Plan activated'
            if purchase.status == 'completed'
            else 'Payment initiated; approve the request on your phone'
        ),
        'purchase': purchase_payload(purchase),
        'entitlement': entitlement_payload(user.id),
    }), 201


@pricing_bp.route('/api/admin/pricing/settings', methods=['GET', 'PATCH'])
@admin_required
def admin_pricing_settings_api():
    if request.method == 'GET':
        return jsonify({
            'settings': serialize_pricing_settings(current_app.config),
            'catalog': serialize_catalog(current_app.config),
        })
    previous = {
        key: bool(current_app.config.get(key, False))
        for key in EDITABLE_PRICING_FLAGS
    }
    try:
        settings = update_pricing_settings(
            request.get_json(silent=True) or {},
            session['user_id'],
            current_app.config,
        )
        log_admin_action(
            session['user_id'],
            'pricing_feature_settings_updated',
            entity_type='pricing_settings',
            summary='Paid plan availability updated',
            details=', '.join(
                f"{item['key']}={str(item['enabled']).lower()}"
                for item in settings['editable']
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
        return jsonify({'error': 'Could not save pricing settings'}), 500
    return jsonify({'message': 'Pricing settings saved', 'settings': settings})
