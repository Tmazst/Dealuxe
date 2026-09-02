"""Persistent allowlisted administrator controls for paid plan sales."""

from datetime import datetime

from database import PricingFeatureSetting, db


EDITABLE_PRICING_FLAGS = (
    'PRICING_ENABLED',
    'PRICING_HYBRID_ENABLED',
    'PRICING_HYBRID_PLUS_ENABLED',
)

LOCKED_PRICING_FLAGS = (
    (
        'PRICING_PREMIUM_ENABLED',
        'Premium sales require the approved live openWA alert adapter',
    ),
)


def _normalize(values):
    values = dict(values)
    if not values['PRICING_ENABLED']:
        values['PRICING_HYBRID_ENABLED'] = False
        values['PRICING_HYBRID_PLUS_ENABLED'] = False
    return values


def _validate_delivery(values, config):
    if values['PRICING_HYBRID_ENABLED'] and not (
        config.get('HYBRID_ENABLED')
        and config.get('HYBRID_PROFILE_ENABLED')
        and config.get('HYBRID_MATCHING_ENABLED')
    ):
        raise ValueError(
            'Enable Hybrid profiles and live matching before selling Hybrid'
        )
    if values['PRICING_HYBRID_PLUS_ENABLED'] and not (
        config.get('HYBRID_ENABLED')
        and config.get('HYBRID_PROFILE_ENABLED')
        and config.get('HYBRID_MATCHING_ENABLED')
        and config.get('HYBRID_BRACKET_DISCOVERY_ENABLED')
    ):
        raise ValueError(
            'Enable Hybrid profiles and open-bracket discovery before selling Hybrid+'
        )


def _effective(config):
    return {key: bool(config.get(key, False)) for key in EDITABLE_PRICING_FLAGS}


def serialize_pricing_settings(config):
    rows = {
        row.setting_key: row
        for row in PricingFeatureSetting.query.filter(
            PricingFeatureSetting.setting_key.in_(EDITABLE_PRICING_FLAGS)
        ).all()
    }
    editable = []
    for key in EDITABLE_PRICING_FLAGS:
        row = rows.get(key)
        editable.append({
            'key': key,
            'enabled': bool(config.get(key, False)),
            'source': 'admin_override' if row else 'environment_default',
            'updated_by': row.updated_by if row else None,
            'updated_at': row.updated_at.isoformat() if row and row.updated_at else None,
        })
    locked = [
        {
            'key': key,
            'enabled': False,
            'editable': False,
            'reason': reason,
        }
        for key, reason in LOCKED_PRICING_FLAGS
    ]
    return {'editable': editable, 'locked': locked}


def update_pricing_settings(payload, admin_user_id, config):
    if not isinstance(payload, dict) or not payload:
        raise ValueError('At least one pricing setting is required')
    unexpected = set(payload) - set(EDITABLE_PRICING_FLAGS)
    if unexpected:
        raise ValueError(
            'Unsupported pricing settings: ' + ', '.join(sorted(unexpected))
        )
    desired = _effective(config)
    for key, value in payload.items():
        if not isinstance(value, bool):
            raise ValueError(f'{key} must be true or false')
        desired[key] = value
    desired = _normalize(desired)
    _validate_delivery(desired, config)

    now = datetime.utcnow()
    for key, enabled in desired.items():
        row = PricingFeatureSetting.query.filter_by(setting_key=key).first()
        if row is None:
            row = PricingFeatureSetting(setting_key=key)
            db.session.add(row)
        row.enabled = enabled
        row.updated_by = admin_user_id
        row.updated_at = now
    db.session.flush()
    config.update(desired)
    return serialize_pricing_settings(config)


def apply_persisted_pricing_settings(app):
    rows = PricingFeatureSetting.query.filter(
        PricingFeatureSetting.setting_key.in_(EDITABLE_PRICING_FLAGS)
    ).all()
    effective = _effective(app.config)
    for row in rows:
        effective[row.setting_key] = bool(row.enabled)
    effective = _normalize(effective)
    # Parent Hybrid switches are incident kill switches. A persisted paid-plan
    # override must never prevent startup or keep selling an unavailable benefit.
    if effective['PRICING_HYBRID_ENABLED'] and not (
        app.config.get('HYBRID_ENABLED')
        and app.config.get('HYBRID_PROFILE_ENABLED')
        and app.config.get('HYBRID_MATCHING_ENABLED')
    ):
        effective['PRICING_HYBRID_ENABLED'] = False
    if effective['PRICING_HYBRID_PLUS_ENABLED'] and not (
        app.config.get('HYBRID_ENABLED')
        and app.config.get('HYBRID_PROFILE_ENABLED')
        and app.config.get('HYBRID_MATCHING_ENABLED')
        and app.config.get('HYBRID_BRACKET_DISCOVERY_ENABLED')
    ):
        effective['PRICING_HYBRID_PLUS_ENABLED'] = False
    app.config.update(effective)
    return effective
