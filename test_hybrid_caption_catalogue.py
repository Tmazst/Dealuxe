import os
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import (
    AdminAuditLog,
    DiscoveryCaptionTemplate,
    Player,
    User,
    db,
)
from hybrid.catalog import ensure_default_caption_templates, render_caption
from hybrid.service import profile_options


class TestHybridCaptionCatalogue(unittest.TestCase):
    def setUp(self):
        self.original_flags = {
            'HYBRID_ENABLED': app.config.get('HYBRID_ENABLED'),
            'HYBRID_PROFILE_ENABLED': app.config.get('HYBRID_PROFILE_ENABLED'),
        }
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        ensure_default_caption_templates()
        self.admin = User(
            username='caption-admin', email='caption-admin@test.com', is_admin=True
        )
        self.admin.set_password('pw')
        self.user = User(username='caption-player', email='caption-player@test.com')
        self.user.set_password('pw')
        db.session.add_all([self.admin, self.user])
        db.session.flush()
        db.session.add_all([
            Player(user_id=self.admin.id),
            Player(user_id=self.user.id),
        ])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original_flags)

    def login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post('/api/auth/login', json={
            'username': user.username,
            'password': 'pw',
        })

    def test_default_catalogue_covers_selling_seeking_and_collaboration(self):
        templates = profile_options()['caption_templates']
        self.assertEqual(len(templates), 6)
        self.assertEqual(
            {template['intent'] for template in templates},
            {'selling', 'seeking', 'collaboration'},
        )
        self.assertTrue(all(template['template_text'] for template in templates))

    def test_admin_can_create_and_edit_audited_caption(self):
        self.login(self.admin)
        response = self.client.post('/api/admin/hybrid/captions', json={
            'code': 'seeking_local_jobs',
            'display_name': 'Seeking local jobs',
            'intent': 'seeking',
            'category': 'jobs',
            'template_text': 'I am seeking {subcategory} work in {location}.',
            'sort_order': 70,
            'is_active': True,
        })
        self.assertEqual(response.status_code, 201)
        caption = response.get_json()['caption']
        self.assertEqual(caption['created_by'], self.admin.id)
        response = self.client.patch(
            f"/api/admin/hybrid/captions/{caption['id']}",
            json={
                'display_name': 'Looking for local work',
                'template_text': 'I am looking for {subcategory} work near {location}.',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()['caption']['display_name'],
            'Looking for local work',
        )
        self.assertEqual(
            AdminAuditLog.query.filter(
                AdminAuditLog.action.in_((
                    'hybrid_caption_template_created',
                    'hybrid_caption_template_updated',
                ))
            ).count(),
            2,
        )

    def test_catalogue_rejects_unsafe_placeholders_and_immutable_code_changes(self):
        self.login(self.admin)
        response = self.client.post('/api/admin/hybrid/captions', json={
            'code': 'unsafe_caption',
            'display_name': 'Unsafe',
            'intent': 'selling',
            'category': 'services',
            'template_text': 'Contact {email} in {location}.',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unsupported template placeholders', response.get_json()['error'])
        response = self.client.post('/api/admin/hybrid/captions', json={
            'code': 'oversized_format',
            'display_name': 'Oversized format',
            'intent': 'selling',
            'category': 'services',
            'template_text': 'Available in {location:1000000}.',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('formatting', response.get_json()['error'])
        template = DiscoveryCaptionTemplate.query.first()
        response = self.client.patch(
            f'/api/admin/hybrid/captions/{template.id}',
            json={'code': 'changed_code'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DiscoveryCaptionTemplate.query.get(template.id).code, template.code)

    def test_deactivated_caption_disappears_and_cannot_be_newly_selected(self):
        template = DiscoveryCaptionTemplate.query.filter_by(
            code='offering_services'
        ).one()
        self.login(self.admin)
        response = self.client.patch(
            f'/api/admin/hybrid/captions/{template.id}',
            json={'is_active': False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            'offering_services', profile_options()['predefined_captions']
        )

        self.login(self.user)
        response = self.client.patch('/api/hybrid/profile', json={
            'intent': 'selling',
            'category': 'services',
            'location': 'Mbabane',
            'predefined_caption': 'offering_services',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('inactive', response.get_json()['error'])

    def test_caption_must_match_profile_intent_and_category(self):
        self.login(self.user)
        response = self.client.patch('/api/hybrid/profile', json={
            'intent': 'seeking',
            'category': 'services',
            'location': 'Manzini',
            'predefined_caption': 'selling_products',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('intent', response.get_json()['error'])

    def test_structured_caption_is_rendered_as_player_preview(self):
        self.login(self.user)
        response = self.client.patch('/api/hybrid/profile', json={
            'is_enabled': True,
            'intent': 'selling',
            'category': 'services',
            'subcategory': 'plumbing',
            'location': 'Mbabane',
            'predefined_caption': 'offering_services',
        })
        self.assertEqual(response.status_code, 200)
        profile = response.get_json()['profile']
        self.assertEqual(
            profile['caption_preview'],
            'I offer plumbing services in Mbabane.',
        )
        page = self.client.get('/account')
        self.assertIn(b'Preview: I offer plumbing services in Mbabane.', page.data)

    def test_renderer_uses_safe_fallback_values_and_length_cap(self):
        template = {
            'template_text': 'Explore {subcategory} in {location} for {category}.'
        }
        self.assertEqual(
            render_caption(template),
            'Explore opportunities in my area for business.',
        )
        long_template = {'template_text': '{subcategory}' * 100}
        self.assertEqual(
            len(render_caption(long_template, subcategory='abcd')),
            280,
        )

    def test_catalogue_endpoints_are_admin_only_even_when_hybrid_is_disabled(self):
        app.config['HYBRID_ENABLED'] = False
        self.login(self.user)
        self.assertEqual(
            self.client.get('/api/admin/hybrid/captions').status_code,
            403,
        )
        self.login(self.admin)
        response = self.client.get('/api/admin/hybrid/captions')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()['captions']), 6)


if __name__ == '__main__':
    unittest.main()
