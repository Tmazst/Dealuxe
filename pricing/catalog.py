"""Single versioned source of truth for Version 3 plan presentation.

Checkout and paid entitlement activation are intentionally outside this
module. Plan wording, prices and future durations can change here without
coupling commercial policy to tournament or Hybrid game logic.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


CATALOG_VERSION = '2026-09-02.1'


@dataclass(frozen=True)
class PricingPlan:
    code: str
    name: str
    price_emalangeni: int
    matching_scope: str
    summary: str
    features: Tuple[str, ...]
    duration_days: Optional[int] = None
    purchasable: bool = False

    def to_dict(self):
        return {
            'code': self.code,
            'name': self.name,
            'price_emalangeni': self.price_emalangeni,
            'currency': 'SZL',
            'matching_scope': self.matching_scope,
            'summary': self.summary,
            'features': list(self.features),
            'duration_days': self.duration_days,
            'purchasable': self.purchasable,
        }


PLANS = (
    PricingPlan(
        code='free',
        name='Free Seeker',
        price_emalangeni=0,
        matching_scope='seeker_visibility',
        summary='Create marketplace demand as a consenting seeker.',
        features=(
            'uMshova Cup qualification eligibility',
            'Multigame tournament brackets',
            'Current seeking caption',
            'Consent-based visibility to eligible sellers',
            'Referral code and referral rewards',
        ),
    ),
    PricingPlan(
        code='hybrid',
        name='Hybrid',
        price_emalangeni=20,
        matching_scope='joined_bracket',
        summary='Potential relevant matching inside a bracket already joined.',
        features=(
            'All Free Seeker features',
            'Seller or promoter profile',
            'Joined-bracket seeker and seller matching',
            'Potential relevant match, subject to available participants',
        ),
    ),
    PricingPlan(
        code='hybrid_plus',
        name='Hybrid+',
        price_emalangeni=40,
        matching_scope='all_open_brackets',
        summary='Discover relevant open brackets before joining.',
        features=(
            'All Hybrid features',
            'Platform-wide eligible open-bracket discovery',
            'Privacy-safe potential seeker badges',
        ),
    ),
    PricingPlan(
        code='premium',
        name='Premium',
        price_emalangeni=60,
        matching_scope='all_open_brackets_with_alerts',
        summary='Receive relevant open-bracket alerts automatically.',
        features=(
            'All Hybrid+ features',
            'Opted-in potential seeker alerts through the future openWA channel',
            'A potential seeker in your category has joined an eligible open bracket',
        ),
    ),
)


def list_plans():
    return tuple(PLANS)


def get_plan(code):
    normalized = str(code or '').strip().lower()
    return next((plan for plan in PLANS if plan.code == normalized), None)


def serialize_catalog(config=None):
    if config is None:
        from flask import current_app
        config = current_app.config
    from .service import PLAN_CONFIG, plan_terms

    serialized = []
    for plan in PLANS:
        row = plan.to_dict()
        if plan.code == 'free':
            row.update(duration_days=None, enabled=True, purchasable=False)
        else:
            flag_key, price_key, duration_key = PLAN_CONFIG[plan.code]
            row.update(
                price_emalangeni=round(float(config[price_key]), 2),
                duration_days=int(config[duration_key]),
                enabled=plan_terms(plan.code, config)['enabled'],
                purchasable=plan_terms(plan.code, config)['enabled'],
            )
        serialized.append(row)
    return {
        'version': CATALOG_VERSION,
        'paid_activation_enabled': bool(config.get('PRICING_ENABLED', False)),
        'billing_period_status': 'configured_non_renewing_passes',
        'plans': serialized,
    }
