"""Persistent, allowlisted administrator controls for safe Hybrid MVP flags."""

from datetime import datetime

from database import HybridFeatureSetting, db


EDITABLE_FLAGS = (
    'HYBRID_ENABLED',
    'HYBRID_PROFILE_ENABLED',
    'HYBRID_MATCHING_SHADOW_ENABLED',
    'HYBRID_MATCHING_ENABLED',
    'HYBRID_CHAT_ENABLED',
)

LOCKED_FLAGS = (
    ('HYBRID_BRACKET_DISCOVERY_ENABLED', 'Public bracket discovery is not implemented'),
    ('HYBRID_PAYMENTS_ENABLED', 'Discovery payments require post-pilot approval'),
    ('HYBRID_RELATIONSHIP_ENABLED', 'Relationship features are unavailable in Version 3'),
)


def _boolean(value, field):
    if isinstance(value, bool):
        return value
    raise ValueError(f'{field} must be true or false')


def _effective_editable(config):
    return {key: bool(config.get(key, False)) for key in EDITABLE_FLAGS}


def _normalize_dependencies(values):
    values = dict(values)
    if not values['HYBRID_ENABLED']:
        values['HYBRID_PROFILE_ENABLED'] = False
        values['HYBRID_MATCHING_SHADOW_ENABLED'] = False
        values['HYBRID_MATCHING_ENABLED'] = False
        values['HYBRID_CHAT_ENABLED'] = False
    elif not values['HYBRID_PROFILE_ENABLED']:
        values['HYBRID_MATCHING_SHADOW_ENABLED'] = False
        values['HYBRID_MATCHING_ENABLED'] = False
        values['HYBRID_CHAT_ENABLED'] = False
    if (
        values['HYBRID_MATCHING_SHADOW_ENABLED']
        and values['HYBRID_MATCHING_ENABLED']
    ):
        raise ValueError('Live matching and shadow matching cannot both be enabled')
    return values


def serialize_settings(config):
    rows = {
        row.setting_key: row
        for row in HybridFeatureSetting.query.filter(
            HybridFeatureSetting.setting_key.in_(EDITABLE_FLAGS)
        ).all()
    }
    editable = []
    for key in EDITABLE_FLAGS:
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
            'enabled': bool(config.get(key, False)),
            'editable': False,
            'reason': reason,
        }
        for key, reason in LOCKED_FLAGS
    ]
    return {'editable': editable, 'locked': locked}


def update_settings(payload, admin_user_id, config):
    if not isinstance(payload, dict):
        raise ValueError('Settings payload must be an object')
    unexpected = set(payload) - set(EDITABLE_FLAGS)
    if unexpected:
        raise ValueError('Unsupported Hybrid settings: ' + ', '.join(sorted(unexpected)))
    if not payload:
        raise ValueError('At least one Hybrid setting is required')
    desired = _effective_editable(config)
    for key, value in payload.items():
        desired[key] = _boolean(value, key)
    desired = _normalize_dependencies(desired)

    now = datetime.utcnow()
    for key, enabled in desired.items():
        row = HybridFeatureSetting.query.filter_by(setting_key=key).first()
        if row is None:
            row = HybridFeatureSetting(setting_key=key)
            db.session.add(row)
        row.enabled = enabled
        row.updated_by = admin_user_id
        row.updated_at = now
    db.session.flush()
    config.update(desired)
    return serialize_settings(config)


def apply_persisted_settings(app):
    """Apply validated database overrides after database initialization."""
    rows = HybridFeatureSetting.query.filter(
        HybridFeatureSetting.setting_key.in_(EDITABLE_FLAGS)
    ).all()
    if not rows:
        return _effective_editable(app.config)
    effective = _effective_editable(app.config)
    for row in rows:
        effective[row.setting_key] = bool(row.enabled)
    effective = _normalize_dependencies(effective)
    app.config.update(effective)
    return effective
