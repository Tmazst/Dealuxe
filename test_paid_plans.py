"""Paid-plan sales, callbacks, access and fail-closed control tests."""

from datetime import datetime, timedelta
import os
import unittest
from unittest.mock import patch

os.environ['ENV'] = 'development'

from app import app
from config import build_pricing_config
from database import (
    AdminAuditLog,
    DiscoveryProfile,
    PlanEntitlement,
    PlanPurchase,
    Player,
    PricingFeatureSetting,
    Tournament,
    TournamentParticipant,
    Transaction,
    User,
    UserBlock,
    db,
)
from pricing.service import entitlement_payload
from pricing.settings import apply_persisted_pricing_settings
from hybrid.shadow import build_participant_snapshots


class PaidPlanTests(unittest.TestCase):
    CONFIG_KEYS = (
        'PRICING_ENABLED', 'PRICING_HYBRID_ENABLED',
        'PRICING_HYBRID_PLUS_ENABLED', 'PRICING_PREMIUM_ENABLED',
        'PRICING_HYBRID_PRICE', 'PRICING_HYBRID_PLUS_PRICE',
        'PRICING_PREMIUM_PRICE', 'PRICING_HYBRID_DURATION_DAYS',
        'PRICING_HYBRID_PLUS_DURATION_DAYS',
        'PRICING_PREMIUM_DURATION_DAYS', 'HYBRID_ENABLED',
        'HYBRID_PROFILE_ENABLED', 'HYBRID_MATCHING_ENABLED',
        'HYBRID_BRACKET_DISCOVERY_ENABLED', 'MOJAPOS_MOCK_MODE',
        'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE',
    )

    def setUp(self):
        self.original = {key: app.config.get(key) for key in self.CONFIG_KEYS}
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            PRICING_ENABLED=True,
            PRICING_HYBRID_ENABLED=True,
            PRICING_HYBRID_PLUS_ENABLED=True,
            PRICING_PREMIUM_ENABLED=False,
            PRICING_HYBRID_PRICE=20.0,
            PRICING_HYBRID_PLUS_PRICE=40.0,
            PRICING_PREMIUM_PRICE=60.0,
            PRICING_HYBRID_DURATION_DAYS=7,
            PRICING_HYBRID_PLUS_DURATION_DAYS=7,
            PRICING_PREMIUM_DURATION_DAYS=7,
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
            HYBRID_MATCHING_ENABLED=True,
            HYBRID_BRACKET_DISCOVERY_ENABLED=True,
            MOJAPOS_MOCK_MODE=False,
            MOJAPOS_VERIFY_WEBHOOK_SIGNATURE=False,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.user = self._user('buyer')
        self.admin = self._user('pricingadmin', is_admin=True)
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original)

    def _user(self, username, is_admin=False):
        user = User(
            username=username,
            email=f'{username}@example.test',
            phone=f'+26876{User.query.count():06d}',
            is_admin=is_admin,
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.flush()
        db.session.add(Player(user_id=user.id))
        db.session.commit()
        return user

    def _login(self, user):
        self.client.post('/api/auth/logout')
        response = self.client.post('/api/auth/login', json={
            'username': user.username,
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 200)

    def _start_live_purchase(self, plan_code='hybrid'):
        self._login(self.user)
        with patch(
            'services.payment_service.payment_service._make_request',
            return_value={
                'transactionId': f'gateway-{plan_code}',
                'providerReference': 'provider-reference',
                'status': 'PENDING',
            },
        ) as request_mock:
            response = self.client.post('/api/pricing/purchases', json={
                'plan_code': plan_code,
            })
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        purchase = PlanPurchase.query.order_by(PlanPurchase.id.desc()).first()
        return response, purchase, request_mock.call_args.kwargs['data']

    def _callback(self, purchase, *, amount=None, currency='SZL', gateway='paid-1'):
        return self.client.post('/api/payment/callback', json={
            'event': 'payment.success',
            'data': {
                'transactionId': gateway,
                'status': 'COMPLETED',
                'amount': str(purchase.amount if amount is None else amount),
                'currency': currency,
                'providerResponse': {'externalId': purchase.external_ref_id},
            },
        })

    def test_configuration_is_default_off_editable_and_premium_is_gated(self):
        config = build_pricing_config({})
        self.assertFalse(config['PRICING_ENABLED'])
        self.assertEqual(config['PRICING_HYBRID_PRICE'], 20.0)
        self.assertEqual(config['PRICING_HYBRID_DURATION_DAYS'], 7)
        configured = build_pricing_config({
            'PRICING_ENABLED': 'true',
            'PRICING_HYBRID_ENABLED': 'true',
            'PRICING_HYBRID_PRICE': '25',
            'PRICING_HYBRID_DURATION_DAYS': '14',
        })
        self.assertEqual(configured['PRICING_HYBRID_PRICE'], 25.0)
        self.assertEqual(configured['PRICING_HYBRID_DURATION_DAYS'], 14)
        with self.assertRaisesRegex(RuntimeError, 'openWA'):
            build_pricing_config({
                'PRICING_ENABLED': 'true',
                'PRICING_PREMIUM_ENABLED': 'true',
            })

    def test_admin_controls_are_protected_persistent_audited_and_fail_closed(self):
        self.assertEqual(self.client.get('/api/admin/pricing/settings').status_code, 401)
        self._login(self.admin)
        response = self.client.patch('/api/admin/pricing/settings', json={
            'PRICING_ENABLED': True,
            'PRICING_HYBRID_ENABLED': True,
            'PRICING_HYBRID_PLUS_ENABLED': True,
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(PricingFeatureSetting.query.count(), 3)
        self.assertEqual(AdminAuditLog.query.filter_by(
            action='pricing_feature_settings_updated'
        ).count(), 1)
        app.config['HYBRID_MATCHING_ENABLED'] = False
        apply_persisted_pricing_settings(app)
        self.assertFalse(app.config['PRICING_HYBRID_ENABLED'])
        self.assertFalse(app.config['PRICING_HYBRID_PLUS_ENABLED'])

    def test_live_purchase_uses_exact_terms_and_waits_for_verified_callback(self):
        response, purchase, payload = self._start_live_purchase('hybrid')
        self.assertEqual(response.get_json()['purchase']['status'], 'pending')
        self.assertEqual(payload['amount'], 20.0)
        self.assertEqual(payload['currency'], 'SZL')
        self.assertEqual(payload['metadata']['externalId'], purchase.external_ref_id)
        self.assertGreaterEqual(len(purchase.external_ref_id), 32)
        self.assertEqual(PlanEntitlement.query.count(), 0)

        callback = self._callback(purchase)
        self.assertEqual(callback.status_code, 200)
        db.session.refresh(purchase)
        self.assertEqual(purchase.status, 'completed')
        self.assertEqual(PlanEntitlement.query.count(), 1)
        self.assertEqual(entitlement_payload(self.user.id)['plan_code'], 'hybrid')

        duplicate = self._callback(purchase)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(PlanEntitlement.query.count(), 1)

    def test_wrong_amount_or_currency_never_activates(self):
        for index, invalid in enumerate(({'amount': 19}, {'currency': 'USD'}), 1):
            _, purchase, _ = self._start_live_purchase('hybrid')
            response = self._callback(
                purchase,
                amount=invalid.get('amount'),
                currency=invalid.get('currency', 'SZL'),
                gateway=f'invalid-{index}',
            )
            self.assertEqual(response.status_code, 200)
            db.session.refresh(purchase)
            self.assertEqual(purchase.status, 'failed')
            self.assertEqual(PlanEntitlement.query.count(), 0)

    def test_explicit_mock_mode_activates_and_repeat_purchase_extends_pass(self):
        app.config['MOJAPOS_MOCK_MODE'] = True
        self._login(self.user)
        first = self.client.post('/api/pricing/purchases', json={'plan_code': 'hybrid'})
        self.assertEqual(first.status_code, 201)
        first_expiry = PlanEntitlement.query.one().expires_at
        second = self.client.post('/api/pricing/purchases', json={'plan_code': 'hybrid'})
        self.assertEqual(second.status_code, 201)
        entitlements = PlanEntitlement.query.order_by(PlanEntitlement.id).all()
        self.assertEqual(len(entitlements), 2)
        self.assertAlmostEqual(
            (entitlements[-1].expires_at - first_expiry).total_seconds(),
            timedelta(days=7).total_seconds(),
            delta=2,
        )
        entitlements[-1].expires_at = datetime.utcnow() - timedelta(seconds=1)
        entitlements[0].expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        self.assertEqual(entitlement_payload(self.user.id)['plan_code'], 'free')

    def test_capability_kill_switch_stops_new_sales_immediately(self):
        app.config['HYBRID_MATCHING_ENABLED'] = False
        self._login(self.user)
        response = self.client.post('/api/pricing/purchases', json={'plan_code': 'hybrid'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlanPurchase.query.count(), 0)
        catalog = self.client.get('/api/pricing/plans').get_json()
        hybrid = next(row for row in catalog['plans'] if row['code'] == 'hybrid')
        self.assertFalse(hybrid['purchasable'])

    def test_account_has_graphical_plan_comparison_and_clear_plan_states(self):
        self._login(self.user)
        response = self.client.get('/account')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('Choose how far your business can reach', page)
        self.assertIn('pricing-grid', page)
        self.assertIn('pricing-card--free', page)
        self.assertIn('pricing-card--hybrid', page)
        self.assertIn('pricing-card--hybrid_plus', page)
        self.assertIn('pricing-card--premium', page)
        self.assertIn('Best reach', page)
        self.assertIn('Awaiting WhatsApp alerts', page)
        self.assertIn('Choose Hybrid', page)

    def test_free_seekers_create_demand_but_sellers_need_an_e20_entitlement(self):
        seller = self._user('entitledseller')
        seeker = self._user('freeseekerdemand')
        db.session.add_all([
            DiscoveryProfile(
                user_id=seller.id, is_enabled=True, is_visible=True,
                intent='selling', category='services',
                moderation_status='not_required',
            ),
            DiscoveryProfile(
                user_id=seeker.id, is_enabled=True, is_visible=True,
                intent='seeking', category='services',
                moderation_status='not_required',
            ),
        ])
        db.session.commit()
        before = {
            row.user_id: row
            for row in build_participant_snapshots(
                [seller.id, seeker.id], app.config
            )
        }
        self.assertFalse(before[seller.id].entitlement_active)
        self.assertTrue(before[seeker.id].entitlement_active)

        app.config['MOJAPOS_MOCK_MODE'] = True
        self._login(seller)
        response = self.client.post('/api/pricing/purchases', json={
            'plan_code': 'hybrid',
        })
        self.assertEqual(response.status_code, 201)
        after = build_participant_snapshots([seller.id], app.config)[0]
        self.assertTrue(after.entitlement_active)
        self.assertEqual(after.plan_level, 1)

    def test_hybrid_plus_badge_is_relevant_but_discloses_no_identity_or_contact(self):
        app.config['MOJAPOS_MOCK_MODE'] = True
        seeker = self._user('privateperson42')
        blocked = self._user('blockedperson84')
        db.session.add_all([
            DiscoveryProfile(
                user_id=self.user.id, is_enabled=True, is_visible=True,
                intent='selling', category='services', subcategory='plumbing',
                predefined_caption='selling_services', moderation_status='not_required',
            ),
            DiscoveryProfile(
                user_id=seeker.id, is_enabled=True, is_visible=True,
                intent='seeking', category='services', subcategory='plumbing',
                custom_caption='Need a plumber; private wording', moderation_status='approved',
            ),
            DiscoveryProfile(
                user_id=blocked.id, is_enabled=True, is_visible=True,
                intent='seeking', category='services', subcategory='plumbing',
                moderation_status='not_required',
            ),
        ])
        tournament = Tournament(
            tournament_code='OPEN-PRIVATE', tournament_name='Open badge bracket',
            tournament_type='standard', creator_id=self.admin.id, entry_fee=0,
            max_players=4, current_player_count=2, status='open',
        )
        db.session.add(tournament)
        db.session.flush()
        db.session.add_all([
            TournamentParticipant(
                tournament_id=tournament.id, user_id=seeker.id,
                status='registered', payment_status='completed',
            ),
            TournamentParticipant(
                tournament_id=tournament.id, user_id=blocked.id,
                status='registered', payment_status='completed',
            ),
            UserBlock(blocker_id=self.user.id, blocked_id=blocked.id, is_active=True),
        ])
        db.session.commit()
        self._login(self.user)
        purchase = self.client.post('/api/pricing/purchases', json={
            'plan_code': 'hybrid_plus',
        })
        self.assertEqual(purchase.status_code, 201)
        response = self.client.get('/api/hybrid/open-brackets/relevance')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload['brackets']), 1)
        self.assertEqual(payload['brackets'][0]['relevance'], 'boosted')
        raw = response.get_data(as_text=True)
        for secret in (
            seeker.username, seeker.email, seeker.phone,
            blocked.username, 'private wording', 'plumbing',
        ):
            self.assertNotIn(secret, raw)


if __name__ == '__main__':
    unittest.main()
