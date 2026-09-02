"""Paid plan purchase, callback activation and expiring entitlements."""

from datetime import datetime, timedelta
import uuid

from flask import current_app

from database import (
    PlanEntitlement,
    PlanPurchase,
    Player,
    Transaction,
    TX_PLAN_PURCHASE,
    db,
)
from services.payment_service import payment_service


PLAN_LEVELS = {'free': 0, 'hybrid': 1, 'hybrid_plus': 2, 'premium': 3}
PLAN_CONFIG = {
    'hybrid': (
        'PRICING_HYBRID_ENABLED',
        'PRICING_HYBRID_PRICE',
        'PRICING_HYBRID_DURATION_DAYS',
    ),
    'hybrid_plus': (
        'PRICING_HYBRID_PLUS_ENABLED',
        'PRICING_HYBRID_PLUS_PRICE',
        'PRICING_HYBRID_PLUS_DURATION_DAYS',
    ),
    'premium': (
        'PRICING_PREMIUM_ENABLED',
        'PRICING_PREMIUM_PRICE',
        'PRICING_PREMIUM_DURATION_DAYS',
    ),
}


def _delivery_available(plan_code, config):
    """Return whether the advertised benefit can be delivered right now."""
    base_hybrid = bool(
        config.get('HYBRID_ENABLED')
        and config.get('HYBRID_PROFILE_ENABLED')
    )
    if plan_code == 'hybrid':
        return base_hybrid and bool(config.get('HYBRID_MATCHING_ENABLED'))
    if plan_code == 'hybrid_plus':
        return bool(
            base_hybrid
            and config.get('HYBRID_MATCHING_ENABLED')
            and config.get('HYBRID_BRACKET_DISCOVERY_ENABLED')
        )
    if plan_code == 'premium':
        return bool(
            base_hybrid
            and config.get('HYBRID_MATCHING_ENABLED')
            and config.get('HYBRID_BRACKET_DISCOVERY_ENABLED')
            and config.get('OPENWA_ENABLED')
            and config.get('OPENWA_ALERTS_ENABLED')
            and config.get('OPENWA_IMPLEMENTATION_STATUS') == 'live'
        )
    return False


def plan_terms(plan_code, config=None):
    config = current_app.config if config is None else config
    plan_code = str(plan_code or '').strip().lower()
    keys = PLAN_CONFIG.get(plan_code)
    if keys is None:
        raise ValueError('Unknown paid plan')
    flag_key, price_key, duration_key = keys
    return {
        'plan_code': plan_code,
        'enabled': bool(
            config.get('PRICING_ENABLED')
            and config.get(flag_key)
            and _delivery_available(plan_code, config)
        ),
        'price': round(float(config[price_key]), 2),
        'duration_days': int(config[duration_key]),
    }


def expire_entitlements(user_id=None, *, now=None):
    now = now or datetime.utcnow()
    query = PlanEntitlement.query.filter(
        PlanEntitlement.status == 'active',
        PlanEntitlement.expires_at <= now,
    )
    if user_id is not None:
        query = query.filter(PlanEntitlement.user_id == int(user_id))
    changed = query.update({'status': 'expired'}, synchronize_session=False)
    if changed:
        db.session.flush()
    return changed


def effective_entitlement(user_id):
    rows = PlanEntitlement.query.filter_by(
        user_id=int(user_id), status='active'
    ).filter(PlanEntitlement.expires_at > datetime.utcnow()).all()
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (PLAN_LEVELS.get(row.plan_code, -1), row.expires_at),
    )


def entitlement_payload(user_id):
    entitlement = effective_entitlement(user_id)
    if entitlement is None:
        return {'plan_code': 'free', 'plan_level': 0, 'expires_at': None}
    return {
        'plan_code': entitlement.plan_code,
        'plan_level': PLAN_LEVELS[entitlement.plan_code],
        'starts_at': entitlement.starts_at.isoformat(),
        'expires_at': entitlement.expires_at.isoformat(),
    }


def has_plan_level(user_id, minimum_code):
    payload = entitlement_payload(user_id)
    return payload['plan_level'] >= PLAN_LEVELS[minimum_code]


def _activate_purchase(purchase, transaction, gateway_transaction_id):
    if purchase.status == 'completed' or transaction.status == 'completed':
        return False
    now = datetime.utcnow()
    same_plan = PlanEntitlement.query.filter_by(
        user_id=purchase.user_id,
        plan_code=purchase.plan_code,
        status='active',
    ).order_by(PlanEntitlement.expires_at.desc()).first()
    starts_at = now
    expiry_base = (
        same_plan.expires_at
        if same_plan and same_plan.expires_at > now
        else now
    )
    entitlement = PlanEntitlement(
        user_id=purchase.user_id,
        plan_code=purchase.plan_code,
        purchase_id=purchase.id,
        status='active',
        starts_at=starts_at,
        expires_at=expiry_base + timedelta(days=purchase.duration_days),
    )
    db.session.add(entitlement)
    purchase.status = 'completed'
    purchase.gateway_transaction_id = gateway_transaction_id
    purchase.completed_at = now
    transaction.status = 'completed'
    transaction.description = gateway_transaction_id or transaction.description
    db.session.flush()
    return True


def handle_plan_payment_callback(
    transaction, status, amount, gateway_transaction_id, currency='SZL'
):
    purchase = PlanPurchase.query.filter_by(transaction_id=transaction.id).first()
    if purchase is None:
        return False
    if purchase.status == 'completed' or transaction.status == 'completed':
        return False
    if status != 'completed':
        if status == 'failed':
            purchase.status = 'failed'
            transaction.status = 'failed'
        return False
    if str(currency or '').strip().upper() != 'SZL':
        purchase.status = 'failed'
        transaction.status = 'failed'
        return False
    if round(float(amount or 0), 2) != round(float(purchase.amount), 2):
        purchase.status = 'failed'
        transaction.status = 'failed'
        return False
    return _activate_purchase(purchase, transaction, gateway_transaction_id)


def initiate_plan_purchase(user, plan_code):
    terms = plan_terms(plan_code)
    if not terms['enabled']:
        raise ValueError('This paid plan is currently unavailable')
    if not user.phone:
        raise ValueError('Add a phone number before purchasing a plan')
    existing = PlanPurchase.query.filter_by(
        user_id=user.id, plan_code=terms['plan_code'], status='pending'
    ).first()
    if existing:
        raise ValueError('A payment for this plan is already pending')
    player = Player.query.filter_by(user_id=user.id).first()
    if player is None:
        raise LookupError('Player wallet not found')

    external_ref_id = uuid.uuid4().hex
    transaction = Transaction(
        player_id=player.id,
        transaction_type=TX_PLAN_PURCHASE,
        amount=terms['price'],
        balance_type='real',
        balance_before=player.real_balance,
        balance_after=player.real_balance,
        external_ref_id=external_ref_id,
        status='initiated',
        description=f"{terms['plan_code']} plan payment pending",
    )
    db.session.add(transaction)
    db.session.flush()
    purchase = PlanPurchase(
        user_id=user.id,
        plan_code=terms['plan_code'],
        amount=terms['price'],
        duration_days=terms['duration_days'],
        status='initiated',
        external_ref_id=external_ref_id,
        transaction_id=transaction.id,
    )
    db.session.add(purchase)
    db.session.flush()

    result = payment_service.initiate_plan_purchase(
        external_ref_id=external_ref_id,
        user_id=user.id,
        amount=terms['price'],
        phone_number=user.phone,
        plan_code=terms['plan_code'],
        txn=transaction,
    )
    if not result.get('success'):
        purchase.status = 'failed'
        transaction.status = 'failed'
        db.session.commit()
        raise RuntimeError(result.get('error') or 'Plan payment initiation failed')

    gateway_id = result.get('external_transaction_id')
    if result.get('mock'):
        _activate_purchase(purchase, transaction, gateway_id)
    else:
        purchase.status = 'pending'
        transaction.status = 'pending'
        transaction.description = gateway_id or transaction.description
    db.session.commit()
    return purchase


def purchase_payload(purchase):
    return {
        'id': purchase.id,
        'plan_code': purchase.plan_code,
        'amount': purchase.amount,
        'currency': 'SZL',
        'duration_days': purchase.duration_days,
        'status': purchase.status,
        'created_at': purchase.created_at.isoformat(),
        'completed_at': (
            purchase.completed_at.isoformat() if purchase.completed_at else None
        ),
    }
