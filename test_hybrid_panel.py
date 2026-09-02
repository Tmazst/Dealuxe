import os
import io
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ['ENV'] = 'development'

from app import app, socketio
from database import (
    DiscoveryProfile,
    GameRoom,
    Tournament,
    TournamentBracket,
    TournamentMatch,
    User,
    UserBlock,
    db,
)


class TestHybridGameContext(unittest.TestCase):
    def setUp(self):
        self.original_config = {
            'TESTING': app.config.get('TESTING'),
            'HYBRID_ENABLED': app.config.get('HYBRID_ENABLED'),
            'HYBRID_PROFILE_ENABLED': app.config.get('HYBRID_PROFILE_ENABLED'),
            'HYBRID_CHAT_ENABLED': app.config.get('HYBRID_CHAT_ENABLED'),
            'PILOT_MODE': app.config.get('PILOT_MODE'),
            'UPLOAD_FOLDER': app.config.get('UPLOAD_FOLDER'),
            'WTF_CSRF_ENABLED': app.config.get('WTF_CSRF_ENABLED'),
        }
        self.upload_folder = tempfile.mkdtemp(prefix='dealuxe-panel-uploads-')
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            UPLOAD_FOLDER=self.upload_folder,
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
            HYBRID_CHAT_ENABLED=False,
            PILOT_MODE=True,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.first = User(username='panel-first', email='panel-first@test.com')
        self.second = User(
            username='panel-second',
            email='panel-second@test.com',
            phone='+26876000000',
        )
        self.outsider = User(username='panel-outsider', email='panel-outsider@test.com')
        for user in (self.first, self.second, self.outsider):
            user.set_password('pw')
        db.session.add_all([self.first, self.second, self.outsider])
        db.session.flush()
        db.session.add_all([
            DiscoveryProfile(
                user_id=self.first.id,
                is_enabled=True,
                is_visible=True,
                intent='seeking',
                category='services',
                subcategory='tailoring',
                location='Manzini',
                predefined_caption='seeking_services',
                moderation_status='not_required',
            ),
            DiscoveryProfile(
                user_id=self.second.id,
                is_enabled=True,
                is_visible=True,
                intent='selling',
                category='services',
                subcategory='tailoring',
                location='Mbabane',
                predefined_caption='offering_services',
                moderation_status='not_required',
            ),
        ])
        db.session.add(GameRoom(
            room_code='PANEL123',
            player1_id=self.first.id,
            player2_id=self.second.id,
            status='in_progress',
        ))
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original_config)
        shutil.rmtree(self.upload_folder, ignore_errors=True)

    def login(self, user):
        self.client.post('/api/auth/logout')
        return self.client.post(
            '/api/auth/login', json={'username': user.username, 'password': 'pw'}
        )

    def test_room_member_receives_only_privacy_safe_opponent_context(self):
        self.login(self.first)
        response = self.client.get('/api/hybrid/game/PANEL123/context')
        self.assertEqual(response.status_code, 200)
        context = response.get_json()['context']
        self.assertTrue(context['available'])
        self.assertTrue(context['own_profile_visible'])
        self.assertEqual(context['opponent']['username'], 'panel-second')
        self.assertEqual(context['opponent']['intent'], 'selling')
        self.assertEqual(context['opponent']['category'], 'services')
        self.assertEqual(context['opponent']['email'], 'panel-second@test.com')
        self.assertEqual(context['opponent']['phone'], '+26876000000')
        self.assertFalse(context['opponent']['has_profile_image'])
        self.assertIsNone(context['opponent']['profile_image_url'])
        self.assertIn('tailoring', context['opponent']['caption'])
        self.assertNotIn('user_id', context['opponent'])
        self.assertNotIn('location', context['opponent'])
        self.assertNotIn('moderation_status', context['opponent'])

    def test_public_profile_image_is_separate_and_room_authorized(self):
        self.login(self.second)
        uploaded = self.client.post(
            '/account/profile-image',
            data={'profile_image': (io.BytesIO(b'profile-image'), 'avatar.jpg')},
            content_type='multipart/form-data',
        )
        self.assertEqual(uploaded.status_code, 302)
        self.assertTrue(db.session.get(User, self.second.id).profile_image_path)

        self.login(self.first)
        context = self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']
        self.assertTrue(context['opponent']['has_profile_image'])
        image_url = context['opponent']['profile_image_url']
        self.assertIn('?v=profile_', image_url)
        self.assertEqual(
            self.client.get(image_url).data,
            b'profile-image',
        )

        self.login(self.outsider)
        self.assertEqual(self.client.get(image_url).status_code, 403)

    def test_outsider_cannot_read_game_context(self):
        self.login(self.outsider)
        response = self.client.get('/api/hybrid/game/PANEL123/context')
        self.assertEqual(response.status_code, 403)

    def test_hidden_or_blocked_profile_falls_back_without_identity(self):
        self.login(self.first)
        profile = DiscoveryProfile.query.filter_by(user_id=self.second.id).one()
        profile.is_visible = False
        db.session.commit()
        hidden = self.client.get('/api/hybrid/game/PANEL123/context').get_json()['context']
        self.assertEqual(hidden, {
            'available': False,
            'reason': 'profile_unavailable',
            'own_profile_visible': True,
        })

        profile.is_visible = True
        db.session.add(UserBlock(blocker_id=self.second.id, blocked_id=self.first.id))
        db.session.commit()
        blocked = self.client.get('/api/hybrid/game/PANEL123/context').get_json()['context']
        self.assertEqual(blocked, {
            'available': False,
            'reason': 'blocked',
            'own_profile_visible': True,
        })

    def test_profile_sharing_is_default_on_and_optional_per_game(self):
        self.login(self.second)
        context = self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']
        self.assertTrue(context['own_profile_visible'])

        response = self.client.put(
            '/api/hybrid/game/PANEL123/preferences',
            json={'profile_visible': False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['profile_visible'])

        self.login(self.first)
        hidden = self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']
        self.assertFalse(hidden['available'])
        self.assertEqual(hidden['reason'], 'hidden_for_game')

    def test_each_player_can_hide_and_unhide_only_their_own_profile(self):
        self.login(self.first)
        self.assertEqual(self.client.put(
            '/api/hybrid/game/PANEL123/preferences',
            json={'profile_visible': False},
        ).status_code, 200)

        self.login(self.second)
        first_hidden = self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']
        self.assertFalse(first_hidden['available'])
        self.assertEqual(first_hidden['reason'], 'hidden_for_game')
        self.assertTrue(first_hidden['own_profile_visible'])
        self.client.put(
            '/api/hybrid/game/PANEL123/preferences',
            json={'profile_visible': False},
        )

        self.login(self.first)
        second_hidden = self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']
        self.assertFalse(second_hidden['available'])
        self.assertEqual(second_hidden['reason'], 'hidden_for_game')
        self.assertFalse(second_hidden['own_profile_visible'])

        self.client.put(
            '/api/hybrid/game/PANEL123/preferences',
            json={'profile_visible': True},
        )
        self.login(self.second)
        first_visible_again = self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']
        self.assertTrue(first_visible_again['available'])
        self.assertFalse(first_visible_again['own_profile_visible'])

        self.client.put(
            '/api/hybrid/game/PANEL123/preferences',
            json={'profile_visible': True},
        )
        self.login(self.first)
        self.assertTrue(self.client.get(
            '/api/hybrid/game/PANEL123/context'
        ).get_json()['context']['available'])

    def test_opponent_receives_immediate_visibility_refresh_event(self):
        second_http = app.test_client()
        second_http.post('/api/auth/login', json={
            'username': self.second.username,
            'password': 'pw',
        })
        second_socket = socketio.test_client(app, flask_test_client=second_http)
        try:
            self.assertTrue(second_socket.is_connected())
            second_socket.get_received()
            self.login(self.first)
            response = self.client.put(
                '/api/hybrid/game/PANEL123/preferences',
                json={'profile_visible': False},
            )
            self.assertEqual(response.status_code, 200)
            events = [
                event for event in second_socket.get_received()
                if event['name'] == 'hybrid_profile_visibility_changed'
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['args'][0]['room_code'], 'PANEL123')
        finally:
            if second_socket.is_connected():
                second_socket.disconnect()

    def test_outsider_cannot_change_game_preferences(self):
        self.login(self.outsider)
        response = self.client.put(
            '/api/hybrid/game/PANEL123/preferences',
            json={'profile_visible': False},
        )
        self.assertEqual(response.status_code, 403)

    def test_disabled_feature_has_no_context_surface(self):
        self.login(self.first)
        app.config['HYBRID_ENABLED'] = False
        self.assertEqual(
            self.client.get('/api/hybrid/game/PANEL123/context').status_code,
            404,
        )

    def test_optional_panel_failure_is_contained_and_game_page_still_loads(self):
        self.login(self.first)
        with patch('hybrid.routes.get_game_context', side_effect=RuntimeError('offline')):
            context = self.client.get('/api/hybrid/game/PANEL123/context')
        self.assertEqual(context.status_code, 503)
        self.assertNotIn('offline', context.get_data(as_text=True))

        game = self.client.get('/game/PANEL123')
        self.assertEqual(game.status_code, 200)
        self.assertIn(b'id="attack-pile"', game.data)
        self.assertNotIn(b'Prize Won', game.data)
        self.assertNotIn(b'Real Money Bet', game.data)
        self.assertNotIn(b'Joining Fee', game.data)
        self.assertNotIn(b'Free Cash', game.data)

    def test_game_page_loads_panel_coordinator(self):
        self.login(self.first)
        response = self.client.get('/game/PANEL123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="hybrid-profile"', response.data)
        self.assertIn(b'/static/js/hybrid-panel.js', response.data)
        self.assertIn(b'/static/css/hybrid-panel.css', response.data)
        self.assertIn(b'id="matchup-me-name">panel-first', response.data)
        self.assertIn(b'id="matchup-opponent-name">panel-second', response.data)
        self.assertIn(b'data-player-avatar="me"', response.data)
        self.assertIn(b'data-player-avatar="opponent"', response.data)
        self.assertIn(b'id="card-count-1"', response.data)
        self.assertIn(b'id="card-count-2"', response.data)

    def test_game_and_qmessanger_have_keyboard_mobile_accessibility_contracts(self):
        self.login(self.first)
        app.config['HYBRID_CHAT_ENABLED'] = True
        page = self.client.get('/game/PANEL123')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'class="skip-link" href="#game-main"', page.data)
        self.assertIn(b'id="game-main" tabindex="-1"', page.data)
        self.assertIn(b'id="hybrid-chat-latest"', page.data)
        self.assertIn(b'role="log"', page.data)
        self.assertIn(b'id="hybrid-chat-status"', page.data)
        self.assertIn(b'role="status"', page.data)
        self.assertIn(b'aria-describedby="hybrid-chat-status"', page.data)

        game_script = self.client.get('/static/js/game.js').get_data(as_text=True)
        self.assertIn("div.setAttribute('role', 'button')", game_script)
        self.assertIn("event.key !== 'Enter' && event.key !== ' '", game_script)
        panel_css = self.client.get(
            '/static/css/hybrid-panel.css'
        ).get_data(as_text=True)
        self.assertIn('@media (max-width: 560px)', panel_css)
        self.assertIn('min-height: 44px', panel_css)
        self.assertIn('prefers-reduced-motion: reduce', panel_css)

    def test_requesting_player_is_always_rendered_on_the_left(self):
        self.login(self.second)
        response = self.client.get('/game/PANEL123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="matchup-me-name">panel-second', response.data)
        self.assertIn(b'id="matchup-opponent-name">panel-first', response.data)

    def test_non_participant_does_not_receive_player_identity(self):
        self.login(self.outsider)
        response = self.client.get('/game/PANEL123')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'panel-first', response.data)
        self.assertNotIn(b'panel-second', response.data)

    def test_tournament_round_field_and_bracket_link_are_displayed(self):
        tournament = Tournament(
            tournament_code='PANEL-T1',
            tournament_name='Panel Tournament',
            tournament_type='standard',
            creator_id=self.first.id,
            entry_fee=0,
            max_players=4,
            current_player_count=4,
            locked_player_count=4,
            status='in_progress',
        )
        db.session.add(tournament)
        db.session.flush()
        bracket = TournamentBracket(
            tournament_id=tournament.id,
            round_number=1,
            round_name='Semi-Final',
            match_number=2,
            player1_id=self.first.id,
            player2_id=self.second.id,
        )
        db.session.add(bracket)
        db.session.flush()
        match = TournamentMatch(
            tournament_id=tournament.id,
            bracket_id=bracket.id,
            game_room_id=GameRoom.query.filter_by(room_code='PANEL123').one().id,
            player1_id=self.first.id,
            player2_id=self.second.id,
            status='in_progress',
        )
        db.session.add(match)
        db.session.flush()
        room = GameRoom.query.filter_by(room_code='PANEL123').one()
        room.tournament_id = tournament.id
        room.match_id = match.id
        db.session.commit()

        self.login(self.second)
        uploaded = self.client.post(
            '/account/profile-image',
            data={'profile_image': (io.BytesIO(b'bracket-avatar'), 'bracket.jpg')},
            content_type='multipart/form-data',
        )
        self.assertEqual(uploaded.status_code, 302)

        self.login(self.first)
        response = self.client.get('/game/PANEL123')
        self.assertIn(b'Panel Tournament', response.data)
        self.assertIn(b'Semi-Final', response.data)
        self.assertIn(b'Match 2', response.data)
        self.assertIn(b'4/4 players', response.data)
        self.assertIn(
            ('/tournaments/{0}/bracket'.format(tournament.id)).encode(),
            response.data,
        )

        overview = self.client.get(
            '/api/tournaments/{0}/overview'.format(tournament.id)
        )
        self.assertEqual(overview.status_code, 200)
        slot = overview.get_json()['rounds'][0]['matches'][0]
        avatar_url = slot['player2_avatar_url']
        self.assertIn('/players/{0}/profile-image?v=profile_'.format(self.second.id), avatar_url)
        image = self.client.get(avatar_url)
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.data, b'bracket-avatar')

        profile = DiscoveryProfile.query.filter_by(user_id=self.second.id).one()
        profile.is_visible = False
        db.session.commit()
        hidden_slot = self.client.get(
            '/api/tournaments/{0}/overview'.format(tournament.id)
        ).get_json()['rounds'][0]['matches'][0]
        self.assertIsNone(hidden_slot['player2_avatar_url'])
        self.assertEqual(self.client.get(avatar_url).status_code, 404)

    def test_chat_composer_is_rendered_only_when_chat_switch_is_enabled(self):
        self.login(self.first)
        disabled = self.client.get('/game/PANEL123')
        self.assertNotIn(b'id="hybrid-chat-form"', disabled.data)
        app.config['HYBRID_CHAT_ENABLED'] = True
        enabled = self.client.get('/game/PANEL123')
        self.assertIn(b'id="hybrid-chat-form"', enabled.data)
        self.assertIn(b'maxlength="280"', enabled.data)


if __name__ == '__main__':
    unittest.main()
