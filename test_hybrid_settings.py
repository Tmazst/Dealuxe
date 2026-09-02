import os
import unittest
from datetime import datetime

os.environ['ENV'] = 'development'

from app import app
from database import (
    AdminAuditLog,
    DiscoveryMatchAudit,
    DiscoveryProfile,
    DiscoveryReport,
    HybridFeatureSetting,
    Player,
    Tournament,
    User,
    UserBlock,
    db,
)
from hybrid.metrics import increment_pilot_counter
from hybrid.settings import apply_persisted_settings


class TestHybridAdminSettings(unittest.TestCase):
    def setUp(self):
        self.editable_flags = (
            'HYBRID_ENABLED',
            'HYBRID_PROFILE_ENABLED',
            'HYBRID_MATCHING_SHADOW_ENABLED',
            'HYBRID_MATCHING_ENABLED',
            'HYBRID_CHAT_ENABLED',
            'HYBRID_BRACKET_DISCOVERY_ENABLED',
        )
        self.original = {
            key: app.config.get(key) for key in self.editable_flags
        }
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            HYBRID_ENABLED=False,
            HYBRID_PROFILE_ENABLED=False,
            HYBRID_MATCHING_SHADOW_ENABLED=False,
            HYBRID_MATCHING_ENABLED=False,
            HYBRID_CHAT_ENABLED=False,
            HYBRID_BRACKET_DISCOVERY_ENABLED=False,
            HYBRID_PAYMENTS_ENABLED=False,
            HYBRID_RELATIONSHIP_ENABLED=False,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(
            username='settings-admin', email='settings-admin@test.com', is_admin=True
        )
        self.admin.set_password('pw')
        self.regular = User(username='settings-user', email='settings-user@test.com')
        self.regular.set_password('pw')
        db.session.add_all([self.admin, self.regular])
        db.session.flush()
        db.session.add_all([
            Player(user_id=self.admin.id),
            Player(user_id=self.regular.id),
        ])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original)

    def login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post('/api/auth/login', json={
            'username': user.username,
            'password': 'pw',
        })

    def test_settings_are_admin_only_but_available_while_hybrid_is_off(self):
        self.assertEqual(
            self.client.get('/api/admin/hybrid/settings').status_code,
            401,
        )
        self.login(self.regular)
        self.assertEqual(
            self.client.get('/api/admin/hybrid/settings').status_code,
            403,
        )
        self.login(self.admin)
        response = self.client.get('/api/admin/hybrid/settings')
        self.assertEqual(response.status_code, 200)
        editable = response.get_json()['settings']['editable']
        self.assertTrue(all(item['enabled'] is False for item in editable))
        self.assertTrue(all(item['source'] == 'environment_default' for item in editable))

    def test_admin_can_enable_profile_and_shadow_with_persistent_audit(self):
        self.login(self.admin)
        response = self.client.patch('/api/admin/hybrid/settings', json={
            'HYBRID_ENABLED': True,
            'HYBRID_PROFILE_ENABLED': True,
            'HYBRID_MATCHING_SHADOW_ENABLED': True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(app.config['HYBRID_ENABLED'])
        self.assertTrue(app.config['HYBRID_PROFILE_ENABLED'])
        self.assertTrue(app.config['HYBRID_MATCHING_SHADOW_ENABLED'])
        self.assertEqual(HybridFeatureSetting.query.count(), 6)
        self.assertEqual(
            AdminAuditLog.query.filter_by(
                action='hybrid_feature_settings_updated'
            ).count(),
            1,
        )

        app.config.update(
            HYBRID_ENABLED=False,
            HYBRID_PROFILE_ENABLED=False,
            HYBRID_MATCHING_SHADOW_ENABLED=False,
        )
        apply_persisted_settings(app)
        self.assertTrue(app.config['HYBRID_MATCHING_SHADOW_ENABLED'])

    def test_disabling_parent_safely_disables_children(self):
        self.login(self.admin)
        self.client.patch('/api/admin/hybrid/settings', json={
            'HYBRID_ENABLED': True,
            'HYBRID_PROFILE_ENABLED': True,
            'HYBRID_MATCHING_SHADOW_ENABLED': True,
        })
        response = self.client.patch('/api/admin/hybrid/settings', json={
            'HYBRID_ENABLED': False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(app.config['HYBRID_ENABLED'])
        self.assertFalse(app.config['HYBRID_PROFILE_ENABLED'])
        self.assertFalse(app.config['HYBRID_MATCHING_SHADOW_ENABLED'])

    def test_chat_is_editable_but_unknown_or_invalid_values_are_rejected(self):
        self.login(self.admin)
        enabled = self.client.patch('/api/admin/hybrid/settings', json={
            'HYBRID_ENABLED': True,
            'HYBRID_PROFILE_ENABLED': True,
            'HYBRID_CHAT_ENABLED': True,
        })
        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(app.config['HYBRID_CHAT_ENABLED'])
        for payload in (
            {'UNKNOWN_SETTING': True},
            {'HYBRID_ENABLED': 'true'},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    '/api/admin/hybrid/settings', json=payload
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(app.config['HYBRID_MATCHING_ENABLED'])
        self.assertTrue(app.config['HYBRID_CHAT_ENABLED'])
        self.assertEqual(HybridFeatureSetting.query.count(), 6)

    def test_admin_can_switch_from_shadow_to_live_but_not_enable_both(self):
        self.login(self.admin)
        response = self.client.patch('/api/admin/hybrid/settings', json={
            'HYBRID_ENABLED': True,
            'HYBRID_PROFILE_ENABLED': True,
            'HYBRID_MATCHING_SHADOW_ENABLED': False,
            'HYBRID_MATCHING_ENABLED': True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(app.config['HYBRID_MATCHING_ENABLED'])
        self.assertFalse(app.config['HYBRID_MATCHING_SHADOW_ENABLED'])
        response = self.client.patch('/api/admin/hybrid/settings', json={
            'HYBRID_MATCHING_SHADOW_ENABLED': True,
            'HYBRID_MATCHING_ENABLED': True,
        })
        self.assertEqual(response.status_code, 400)

    def test_admin_page_contains_settings_and_caption_status(self):
        self.login(self.admin)
        response = self.client.get('/api/admin/admin')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Hybrid MVP Settings', response.data)
        self.assertIn(b'Hybrid Caption Catalogue', response.data)
        self.assertIn(b'settingHybridChat', response.data)
        self.assertIn(b'settingHybridDiscovery', response.data)
        self.assertIn(b'Paid Plan Settings', response.data)
        self.assertIn(b'Hybrid MVP Pilot Measurements', response.data)
        self.assertIn(b'Manage seeking, selling and collaboration wording', response.data)
        self.assertIn(b'Locked for this MVP stage', response.data)
        self.assertIn(b'name="viewport"', response.data)
        self.assertIn(b'class="skip-link" href="#admin-main"', response.data)
        self.assertIn(b'<main id="admin-main" tabindex="-1">', response.data)
        self.assertIn(b'aria-label="uMshova Cup qualification roster"', response.data)
        self.assertIn(b'aria-label="Hybrid safety reports"', response.data)
        self.assertIn(b'aria-label="Hybrid matching audits"', response.data)
        self.assertIn(b'@media (max-width: 700px)', response.data)
        self.assertIn(b'prefers-reduced-motion: reduce', response.data)

    def test_privacy_safe_pilot_measurements_are_admin_only_and_aggregated(self):
        profile = DiscoveryProfile(
            user_id=self.regular.id,
            is_enabled=True,
            is_visible=True,
            intent='seeking',
            category='services',
            location='Manzini',
            predefined_caption='seeking_services',
            custom_caption='private caption must never appear in metrics',
        )
        tournament = Tournament(
            tournament_code='METRICS-1',
            tournament_name='Pilot Metrics Tournament',
            tournament_type='standard',
            creator_id=self.admin.id,
            entry_fee=0,
            max_players=4,
            current_player_count=4,
            status='completed',
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.session.add_all([profile, tournament])
        db.session.flush()
        db.session.add_all([
            DiscoveryMatchAudit(
                tournament_id=tournament.id,
                mode='live',
                algorithm_version='metrics-test-v1',
                status='matched',
                participant_count=4,
                total_score=95,
                hybrid_pair_count=1,
                matching_duration_ms=12.5,
                legacy_fallback_recommended=False,
                proposed_seed_order_json='[]',
                legacy_seed_order_json='[]',
                pairs_json='[]',
            ),
            UserBlock(
                blocker_id=self.admin.id,
                blocked_id=self.regular.id,
                is_active=True,
            ),
            DiscoveryReport(
                reporter_id=self.admin.id,
                reported_user_id=self.regular.id,
                profile_id=profile.id,
                reason_code='other',
                details='private report details must never appear in metrics',
                status='pending',
            ),
        ])
        db.session.commit()
        increment_pilot_counter('chat_messages_delivered', 2)
        increment_pilot_counter('chat_storage_failures')

        self.login(self.regular)
        self.assertEqual(
            self.client.get('/api/admin/hybrid/pilot-metrics').status_code,
            403,
        )
        self.login(self.admin)
        response = self.client.get('/api/admin/hybrid/pilot-metrics')
        self.assertEqual(response.status_code, 200)
        metrics = response.get_json()['metrics']
        self.assertEqual(metrics['adoption']['opt_in_rate_pct'], 50.0)
        self.assertEqual(metrics['adoption']['profile_completion_rate_pct'], 100.0)
        self.assertEqual(metrics['matching']['relevant_pairs'], 1)
        self.assertEqual(metrics['matching']['game_only_pairs'], 1)
        self.assertEqual(metrics['matching']['average_latency_ms'], 12.5)
        self.assertEqual(metrics['qmessanger']['messages_delivered'], 2)
        self.assertEqual(metrics['qmessanger']['storage_failures'], 1)
        self.assertEqual(metrics['safety']['active_blocks'], 1)
        self.assertEqual(metrics['safety']['reports_awaiting_action'], 1)
        self.assertEqual(metrics['tournaments']['completion_rate_pct'], 100.0)
        payload = response.get_data(as_text=True)
        self.assertNotIn('private caption', payload)
        self.assertNotIn('private report details', payload)


if __name__ == '__main__':
    unittest.main()
