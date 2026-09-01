import os
import unittest

os.environ['ENV'] = 'development'

from app import app, socketio
from database import DiscoveryProfile, GameRoom, HybridPilotMetric, User, UserBlock, db
from hybrid.chat import MemoryChatStore


class TestMemoryChatStore(unittest.TestCase):
    def test_messages_and_replay_claims_expire(self):
        now = [1000.0]
        store = MemoryChatStore(ttl_seconds=10, clock=lambda: now[0])
        message = {
            'id': 'one', 'room_code': 'ROOM1', 'sender_id': 1,
            'message': 'hello', 'sent_at': 1000,
        }
        self.assertTrue(store.claim_message('ROOM1', 1, 'client_one'))


class FailingChatStore:
    """Simulate a complete optional chat-storage outage."""

    def latest(self, room_code):
        raise RuntimeError('chat storage offline')

    def claim_message(self, room_code, user_id, client_message_id):
        raise RuntimeError('chat storage offline')
        self.assertFalse(store.claim_message('ROOM1', 1, 'client_one'))
        store.add('ROOM1', message)
        self.assertEqual(store.latest('ROOM1')['message'], 'hello')
        now[0] = 1011.0
        self.assertIsNone(store.latest('ROOM1'))
        self.assertTrue(store.claim_message('ROOM1', 1, 'client_one'))


class TestHybridChatEvents(unittest.TestCase):
    def setUp(self):
        self.original = {
            key: app.config.get(key) for key in (
                'TESTING', 'HYBRID_ENABLED', 'HYBRID_PROFILE_ENABLED',
                'HYBRID_CHAT_ENABLED',
            )
        }
        app.config.update(
            TESTING=True,
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
            HYBRID_CHAT_ENABLED=True,
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.first = self._user('chat-first')
        self.second = self._user('chat-second')
        self.outsider = self._user('chat-outsider')
        db.session.flush()
        for user in (self.first, self.second):
            db.session.add(DiscoveryProfile(
                user_id=user.id,
                is_enabled=True,
                is_visible=True,
                chat_preference_enabled=True,
                intent='selling',
                category='services',
                predefined_caption='offering_services',
            ))
        self.room = GameRoom(
            room_code='CHATROOM',
            player1_id=self.first.id,
            player2_id=self.second.id,
            status='in_progress',
        )
        db.session.add(self.room)
        db.session.commit()
        app.extensions['hybrid_chat_store'] = MemoryChatStore()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            if client.is_connected():
                client.disconnect()
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.config.update(self.original)

    @staticmethod
    def _user(username):
        user = User(username=username, email=username + '@test.com')
        user.set_password('pw')
        db.session.add(user)
        return user

    def _socket(self, user):
        http = app.test_client()
        response = http.post('/api/auth/login', json={
            'username': user.username, 'password': 'pw',
        })
        self.assertEqual(response.status_code, 200)
        client = socketio.test_client(app, flask_test_client=http)
        self.assertTrue(client.is_connected())
        client.get_received()
        self.clients.append(client)
        return client

    @staticmethod
    def _event(client, name):
        return [item for item in client.get_received() if item['name'] == name]

    def test_two_room_members_exchange_private_personalized_message(self):
        first = self._socket(self.first)
        second = self._socket(self.second)
        first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        context = self._event(first, 'hybrid_chat_context')[0]['args'][0]
        self.assertTrue(context['available'])
        self.assertIsNone(context['latest'])

        first.emit('hybrid_chat_send', {
            'room_code': 'CHATROOM',
            'message': '<b>Hello</b>',
            'client_message_id': 'client_12345678',
        })
        own = self._event(first, 'hybrid_chat_message')[0]['args'][0]
        received = self._event(second, 'hybrid_chat_message')[0]['args'][0]
        self.assertEqual(own['sender'], 'you')
        self.assertEqual(received['sender'], 'opponent')
        self.assertEqual(received['message'], '<b>Hello</b>')
        self.assertEqual(
            HybridPilotMetric.query.filter_by(
                metric_key='chat_messages_delivered'
            ).one().total_count,
            1,
        )

        second.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        reconnect = self._event(second, 'hybrid_chat_context')[0]['args'][0]
        self.assertEqual(reconnect['latest']['message'], '<b>Hello</b>')
        self.assertEqual(reconnect['latest']['sender'], 'opponent')

    def test_outsider_and_cross_room_spoof_are_denied(self):
        outsider = self._socket(self.outsider)
        outsider.emit('hybrid_chat_send', {
            'room_code': 'CHATROOM', 'message': 'No access',
            'client_message_id': 'outsider_12345678',
        })
        error = self._event(outsider, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(error['code'], 'not_room_member')
        self.assertIsNone(app.extensions['hybrid_chat_store'].latest('CHATROOM'))

    def test_block_or_disabled_preference_stops_chat(self):
        first = self._socket(self.first)
        profile = DiscoveryProfile.query.filter_by(user_id=self.second.id).one()
        profile.chat_preference_enabled = False
        db.session.commit()
        first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        context = self._event(first, 'hybrid_chat_context')[0]['args'][0]
        self.assertFalse(context['available'])
        self.assertEqual(context['reason'], 'chat_preference_required')

        profile.chat_preference_enabled = True
        db.session.add(UserBlock(
            blocker_id=self.second.id, blocked_id=self.first.id, is_active=True
        ))
        db.session.commit()
        first.emit('hybrid_chat_send', {
            'room_code': 'CHATROOM', 'message': 'Blocked',
            'client_message_id': 'blocked_12345678',
        })
        error = self._event(first, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(error['code'], 'blocked')

    def test_either_players_per_game_hide_choice_disables_chat_for_both(self):
        first = self._socket(self.first)
        second = self._socket(self.second)

        self.room.player1_profile_visible = False
        db.session.commit()
        for client in (first, second):
            client.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
            context = self._event(client, 'hybrid_chat_context')[0]['args'][0]
            self.assertFalse(context['available'])
            self.assertEqual(context['reason'], 'hidden_for_game')

        self.room.player1_profile_visible = True
        self.room.player2_profile_visible = False
        db.session.commit()
        for client in (first, second):
            client.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
            context = self._event(client, 'hybrid_chat_context')[0]['args'][0]
            self.assertFalse(context['available'])
            self.assertEqual(context['reason'], 'hidden_for_game')

    def test_duplicate_control_character_and_rate_limits_are_enforced(self):
        first = self._socket(self.first)
        payload = {
            'room_code': 'CHATROOM', 'message': 'Once',
            'client_message_id': 'repeat_12345678',
        }
        first.emit('hybrid_chat_send', payload)
        self._event(first, 'hybrid_chat_message')
        first.emit('hybrid_chat_send', payload)
        duplicate = self._event(first, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(duplicate['code'], 'duplicate_message')

        first.emit('hybrid_chat_send', {
            'room_code': 'CHATROOM', 'message': 'bad\nmessage',
            'client_message_id': 'control_12345678',
        })
        invalid = self._event(first, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(invalid['code'], 'invalid_message')

        for number in range(4):
            first.emit('hybrid_chat_send', {
                'room_code': 'CHATROOM', 'message': 'Message ' + str(number),
                'client_message_id': 'rate_{0}_12345678'.format(number),
            })
            self._event(first, 'hybrid_chat_message')
        first.emit('hybrid_chat_send', {
            'room_code': 'CHATROOM', 'message': 'Too fast',
            'client_message_id': 'rate_final_12345678',
        })
        limited = self._event(first, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(limited['code'], 'rate_limited')

    def test_disabled_feature_fails_closed(self):
        first = self._socket(self.first)
        app.config['HYBRID_CHAT_ENABLED'] = False
        first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        context = self._event(first, 'hybrid_chat_context')[0]['args'][0]
        self.assertFalse(context['available'])
        self.assertEqual(context['reason'], 'chat_disabled')

    def test_storage_failure_returns_chat_error_without_ending_game_session(self):
        first = self._socket(self.first)
        app.extensions['hybrid_chat_store'] = FailingChatStore()

        first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        context_error = self._event(first, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(context_error['code'], 'storage_unavailable')
        self.assertTrue(first.is_connected())

        first.emit('hybrid_chat_send', {
            'room_code': 'CHATROOM',
            'message': 'Gameplay must continue',
            'client_message_id': 'storage_12345678',
        })
        send_error = self._event(first, 'hybrid_chat_error')[0]['args'][0]
        self.assertEqual(send_error['code'], 'storage_unavailable')
        self.assertTrue(first.is_connected())
        self.assertEqual(db.session.get(GameRoom, self.room.id).status, 'in_progress')
        self.assertEqual(
            HybridPilotMetric.query.filter_by(
                metric_key='chat_storage_failures'
            ).one().total_count,
            2,
        )


if __name__ == '__main__':
    unittest.main()
