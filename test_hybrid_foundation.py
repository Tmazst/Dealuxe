import os
import unittest

os.environ['ENV'] = 'development'

from app import app
from config import build_hybrid_config
from database import (
    AdminAuditLog,
    DiscoveryProfile,
    DiscoveryReport,
    Player,
    User,
    UserBlock,
    db,
)
from hybrid.service import users_are_blocked


class TestHybridConfiguration(unittest.TestCase):
    def test_hybrid_is_disabled_by_default(self):
        config = build_hybrid_config({})
        self.assertEqual(config['HYBRID_MATCHING_TIMEOUT_MS'], 250)
        self.assertTrue(all(
            value is False
            for key, value in config.items()
            if key != 'HYBRID_MATCHING_TIMEOUT_MS'
        ))

    def test_profile_requires_master_switch(self):
        with self.assertRaisesRegex(RuntimeError, 'HYBRID_ENABLED'):
            build_hybrid_config({'HYBRID_PROFILE_ENABLED': 'true'})

    def test_only_profile_foundation_can_be_enabled(self):
        config = build_hybrid_config({
            'HYBRID_ENABLED': 'true',
            'HYBRID_PROFILE_ENABLED': 'true',
        })
        self.assertTrue(config['HYBRID_ENABLED'])
        self.assertTrue(config['HYBRID_PROFILE_ENABLED'])
        for flag in (
            'HYBRID_CHAT_ENABLED',
            'HYBRID_MATCHING_SHADOW_ENABLED',
            'HYBRID_BRACKET_DISCOVERY_ENABLED', 'HYBRID_PAYMENTS_ENABLED',
            'HYBRID_RELATIONSHIP_ENABLED',
        ):
            self.assertFalse(config[flag])

    def test_unimplemented_or_post_pilot_features_fail_closed(self):
        for flag in (
            'HYBRID_MATCHING_ENABLED',
            'HYBRID_PAYMENTS_ENABLED',
            'HYBRID_RELATIONSHIP_ENABLED',
        ):
            with self.subTest(flag=flag), self.assertRaises(RuntimeError):
                build_hybrid_config({'HYBRID_ENABLED': 'true', flag: 'true'})

    def test_bracket_discovery_requires_profiles_and_can_be_enabled(self):
        with self.assertRaisesRegex(RuntimeError, 'HYBRID_PROFILE_ENABLED'):
            build_hybrid_config({
                'HYBRID_ENABLED': 'true',
                'HYBRID_BRACKET_DISCOVERY_ENABLED': 'true',
            })
        config = build_hybrid_config({
            'HYBRID_ENABLED': 'true',
            'HYBRID_PROFILE_ENABLED': 'true',
            'HYBRID_BRACKET_DISCOVERY_ENABLED': 'true',
        })
        self.assertTrue(config['HYBRID_BRACKET_DISCOVERY_ENABLED'])

    def test_chat_requires_master_and_can_be_enabled_with_profiles(self):
        with self.assertRaisesRegex(RuntimeError, 'HYBRID_ENABLED'):
            build_hybrid_config({'HYBRID_CHAT_ENABLED': 'true'})
        config = build_hybrid_config({
            'HYBRID_ENABLED': 'true',
            'HYBRID_PROFILE_ENABLED': 'true',
            'HYBRID_CHAT_ENABLED': 'true',
        })
        self.assertTrue(config['HYBRID_CHAT_ENABLED'])

    def test_live_matching_requires_profiles_and_is_mutually_exclusive_with_shadow(self):
        with self.assertRaisesRegex(RuntimeError, 'HYBRID_PROFILE_ENABLED'):
            build_hybrid_config({
                'HYBRID_ENABLED': 'true',
                'HYBRID_MATCHING_ENABLED': 'true',
            })
        config = build_hybrid_config({
            'HYBRID_ENABLED': 'true',
            'HYBRID_PROFILE_ENABLED': 'true',
            'HYBRID_MATCHING_ENABLED': 'true',
        })
        self.assertTrue(config['HYBRID_MATCHING_ENABLED'])
        with self.assertRaisesRegex(RuntimeError, 'either'):
            build_hybrid_config({
                'HYBRID_ENABLED': 'true',
                'HYBRID_PROFILE_ENABLED': 'true',
                'HYBRID_MATCHING_ENABLED': 'true',
                'HYBRID_MATCHING_SHADOW_ENABLED': 'true',
            })

    def test_shadow_mode_requires_master_and_profile_but_not_live_matching(self):
        with self.assertRaisesRegex(RuntimeError, 'HYBRID_PROFILE_ENABLED'):
            build_hybrid_config({
                'HYBRID_ENABLED': 'true',
                'HYBRID_MATCHING_SHADOW_ENABLED': 'true',
            })
        config = build_hybrid_config({
            'HYBRID_ENABLED': 'true',
            'HYBRID_PROFILE_ENABLED': 'true',
            'HYBRID_MATCHING_SHADOW_ENABLED': 'true',
        })
        self.assertTrue(config['HYBRID_MATCHING_SHADOW_ENABLED'])
        self.assertFalse(config['HYBRID_MATCHING_ENABLED'])


class TestHybridProfileFoundation(unittest.TestCase):
    def setUp(self):
        self.hybrid_flags = (
            'HYBRID_ENABLED', 'HYBRID_PROFILE_ENABLED',
            'HYBRID_MATCHING_ENABLED', 'HYBRID_CHAT_ENABLED',
            'HYBRID_MATCHING_SHADOW_ENABLED',
            'HYBRID_BRACKET_DISCOVERY_ENABLED', 'HYBRID_PAYMENTS_ENABLED',
            'HYBRID_RELATIONSHIP_ENABLED',
        )
        self.original_hybrid_config = {
            flag: app.config.get(flag) for flag in self.hybrid_flags
        }
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            HYBRID_ENABLED=False,
            HYBRID_PROFILE_ENABLED=False,
            HYBRID_MATCHING_ENABLED=False,
            HYBRID_MATCHING_SHADOW_ENABLED=False,
            HYBRID_CHAT_ENABLED=False,
            HYBRID_BRACKET_DISCOVERY_ENABLED=False,
            HYBRID_PAYMENTS_ENABLED=False,
            HYBRID_RELATIONSHIP_ENABLED=False,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.user = User(username='hybrid-player', email='hybrid@test.com')
        self.user.set_password('pw')
        self.admin = User(
            username='hybrid-admin', email='hybrid-admin@test.com', is_admin=True
        )
        self.admin.set_password('pw')
        self.other = User(username='hybrid-other', email='hybrid-other@test.com')
        self.other.set_password('pw')
        db.session.add_all([self.user, self.admin, self.other])
        db.session.flush()
        db.session.add_all([
            Player(user_id=self.user.id),
            Player(user_id=self.admin.id),
            Player(user_id=self.other.id),
        ])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original_hybrid_config)

    def login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post(
            '/api/auth/login', json={'username': user.username, 'password': 'pw'}
        )

    def enable_profile_foundation(self):
        app.config['HYBRID_ENABLED'] = True
        app.config['HYBRID_PROFILE_ENABLED'] = True

    def test_disabled_hybrid_has_no_account_or_api_surface(self):
        self.login(self.user)
        self.assertEqual(self.client.get('/api/hybrid/profile').status_code, 404)
        page = self.client.get('/account')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Discovery &amp; Matching', page.data)
        account = self.client.get('/account/api').get_json()['account']
        self.assertNotIn('discovery_profile', account)
        self.assertEqual(DiscoveryProfile.query.count(), 0)

    def test_owner_can_create_private_profile(self):
        self.enable_profile_foundation()
        self.login(self.user)
        response = self.client.patch('/api/hybrid/profile', json={
            'is_enabled': True,
            'intent': 'selling',
            'category': 'services',
            'subcategory': 'repairs',
            'location': 'Mbabane',
            'predefined_caption': 'offering_services',
            'custom_caption': 'I repair household appliances.',
            'is_visible': True,
            'chat_preference_enabled': True,
        })
        self.assertEqual(response.status_code, 200)
        profile = response.get_json()['profile']
        self.assertEqual(profile['moderation_status'], 'pending_review')
        self.assertTrue(profile['is_enabled'])
        self.assertEqual(DiscoveryProfile.query.count(), 1)

        page = self.client.get('/account')
        self.assertIn(b'Hybrid Discovery', page.data)
        account = self.client.get('/account/api').get_json()['account']
        self.assertEqual(account['discovery_profile']['location'], 'Mbabane')

    def test_profile_updates_use_a_strict_allowlist(self):
        self.enable_profile_foundation()
        self.login(self.user)
        response = self.client.patch(
            '/api/hybrid/profile', json={'user_id': self.admin.id}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DiscoveryProfile.query.count(), 0)

    def test_enabled_profile_requires_minimum_discovery_fields(self):
        self.enable_profile_foundation()
        self.login(self.user)
        response = self.client.patch(
            '/api/hybrid/profile', json={'is_enabled': True}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('intent is required', response.get_json()['error'])

    def test_admin_can_view_profiles_but_regular_user_cannot(self):
        self.enable_profile_foundation()
        self.login(self.user)
        self.client.patch('/api/hybrid/profile', json={
            'intent': 'seeking',
            'category': 'products',
            'location': 'Manzini',
            'predefined_caption': 'looking_to_buy',
        })
        self.assertEqual(
            self.client.get('/api/admin/hybrid/profiles').status_code, 403
        )

        self.login(self.admin)
        response = self.client.get('/api/admin/hybrid/profiles')
        self.assertEqual(response.status_code, 200)
        profiles = response.get_json()['profiles']
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]['username'], self.user.username)

    def test_matching_chat_and_public_discovery_are_not_exposed(self):
        self.enable_profile_foundation()
        self.login(self.user)
        for path in (
            '/api/hybrid/matches',
            '/api/hybrid/chat',
            '/api/hybrid/discovery',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_block_is_a_mutual_hard_exclusion_and_can_be_reversed(self):
        self.enable_profile_foundation()
        self.login(self.user)
        response = self.client.post(
            '/api/hybrid/blocks', json={'blocked_user_id': self.other.id}
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(users_are_blocked(self.user.id, self.other.id))
        self.assertTrue(users_are_blocked(self.other.id, self.user.id))
        self.assertEqual(UserBlock.query.filter_by(is_active=True).count(), 1)

        blocks = self.client.get('/api/hybrid/blocks').get_json()['blocks']
        self.assertEqual(blocks[0]['blocked_username'], self.other.username)
        response = self.client.delete(f'/api/hybrid/blocks/{self.other.id}')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(users_are_blocked(self.user.id, self.other.id))

    def test_block_and_report_reject_self_or_unknown_targets(self):
        self.enable_profile_foundation()
        self.login(self.user)
        self.assertEqual(self.client.post(
            '/api/hybrid/blocks', json={'blocked_user_id': self.user.id}
        ).status_code, 400)
        self.assertEqual(self.client.post('/api/hybrid/reports', json={
            'reported_user_id': 999999,
            'reason_code': 'spam',
        }).status_code, 404)
        self.assertEqual(self.client.post('/api/hybrid/reports', json={
            'reported_user_id': self.other.id,
            'reason_code': 'not-a-valid-reason',
        }).status_code, 400)

    def test_admin_caption_decision_is_audited_and_rejection_hides_profile(self):
        self.enable_profile_foundation()
        self.login(self.user)
        profile = self.client.patch('/api/hybrid/profile', json={
            'is_enabled': True,
            'intent': 'selling',
            'category': 'services',
            'location': 'Mbabane',
            'custom_caption': 'Custom wording for review',
            'is_visible': True,
        }).get_json()['profile']
        self.assertEqual(profile['moderation_status'], 'pending_review')
        self.assertFalse(profile['is_visible'])

        self.login(self.admin)
        response = self.client.patch(
            f"/api/admin/hybrid/profiles/{profile['id']}/moderation",
            json={'decision': 'rejected', 'note': 'Needs safer wording'},
        )
        self.assertEqual(response.status_code, 200)
        moderated = response.get_json()['profile']
        self.assertEqual(moderated['moderation_status'], 'rejected')
        self.assertFalse(moderated['is_visible'])
        self.assertEqual(moderated['moderated_by'], self.admin.id)
        self.assertEqual(
            AdminAuditLog.query.filter_by(action='hybrid_caption_moderated').count(),
            1,
        )

        self.login(self.user)
        attempted = self.client.patch(
            '/api/hybrid/profile', json={'is_visible': True}
        ).get_json()['profile']
        self.assertFalse(attempted['is_visible'])

    def test_report_lifecycle_is_private_and_admin_audited(self):
        self.enable_profile_foundation()
        self.login(self.user)
        response = self.client.post('/api/hybrid/reports', json={
            'reported_user_id': self.other.id,
            'reason_code': 'spam',
            'details': 'Repeated unwanted promotional messages.',
        })
        self.assertEqual(response.status_code, 201)
        report_id = response.get_json()['report']['id']
        own = self.client.get('/api/hybrid/reports').get_json()['reports']
        self.assertEqual(len(own), 1)
        self.assertNotIn('reporter_id', own[0])

        self.login(self.other)
        self.assertEqual(self.client.get('/api/hybrid/reports').get_json()['reports'], [])
        self.assertEqual(
            self.client.get('/api/admin/hybrid/reports').status_code, 403
        )

        self.login(self.admin)
        reports = self.client.get(
            '/api/admin/hybrid/reports?status=pending'
        ).get_json()['reports']
        self.assertEqual(reports[0]['reporter_username'], self.user.username)
        response = self.client.patch(
            f'/api/admin/hybrid/reports/{report_id}',
            json={'status': 'resolved', 'resolution': 'Reviewed and handled.'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['report']['status'], 'resolved')
        self.assertEqual(db.session.get(DiscoveryReport, report_id).reviewed_by, self.admin.id)
        self.assertEqual(
            AdminAuditLog.query.filter_by(action='hybrid_report_reviewed').count(),
            1,
        )


if __name__ == '__main__':
    unittest.main()
