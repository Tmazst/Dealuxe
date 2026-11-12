import os
import unittest
from unittest.mock import patch

os.environ['ENV'] = 'development'

from app import app, socketio
from database import DiscoveryProfile, GameRoom, HybridPilotMetric, MatchChatPushSubscription, User, UserBlock, db
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

    def test_push_only_for_messages_unseen_in_the_game(self):
        first = self._socket(self.first)
        second = self._socket(self.second)
        settings = {
            'MATCH_CHAT_PUSH_PUBLIC_KEY': 'public',
            'MATCH_CHAT_PUSH_PRIVATE_KEY': 'private',
            'MATCH_CHAT_PUSH_SUBJECT': 'mailto:ops@example.com',
        }
        with patch.dict(app.config, settings), patch.object(socketio, 'sleep'), \
                patch.object(socketio, 'start_background_task') as schedule, \
                patch('hybrid.chat.send_match_chat_push') as push:
            for number, seen in enumerate((True, False)):
                first.emit('hybrid_chat_send', {
                    'room_code': 'CHATROOM',
                    'message': 'Hello',
                    'client_message_id': 'push_test_' + str(number),
                })
                message = self._event(second, 'hybrid_chat_message')[0]['args'][0]
                if seen:
                    second.emit('hybrid_chat_seen', {'room_code': 'CHATROOM', 'id': message['id']})
                task, *arguments = schedule.call_args.args
                task(*arguments)
                if seen:
                    push.assert_not_called()
            push.assert_called_once()
            recipient, payload, url = push.call_args.args
            self.assertEqual(recipient, self.second.id)
            self.assertEqual(payload['message'], 'Hello')
            self.assertEqual(url, '/game/CHATROOM')

    def test_push_subscription_is_private_and_removed_on_logout(self):
        path = '/api/match-chat/push'
        client = app.test_client()
        self.assertEqual(client.get(path).status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json={
            'username': self.first.username, 'password': 'pw',
        }).status_code, 200)
        token = client.get('/api/security/csrf-token').get_json()['csrf_token']
        headers = {'X-CSRF-Token': token}
        subscription = {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/example',
            'keys': {'auth': 'A' * 22, 'p256dh': 'B' * 87},
        }
        with patch.dict(app.config, {
            'MATCH_CHAT_PUSH_PUBLIC_KEY': 'public',
            'MATCH_CHAT_PUSH_PRIVATE_KEY': 'private',
            'MATCH_CHAT_PUSH_SUBJECT': 'mailto:ops@example.com',
        }):
            self.assertEqual(client.post(path, headers=headers, json={
                **subscription, 'endpoint': 'https://fcm.googleapis.com.example.org/push',
            }).status_code, 400)
            self.assertEqual(client.post(path, headers=headers, json=subscription).status_code, 204)
            settings = client.get(path).get_json()
            self.assertEqual(settings, {'public_key': 'public', 'subscribed': True})
            self.assertEqual(MatchChatPushSubscription.query.one().user_id, self.first.id)
            self.assertEqual(client.post('/logout', headers=headers, json={}).status_code, 200)
            self.assertEqual(MatchChatPushSubscription.query.count(), 0)

    def test_block_or_disabled_preference_stops_chat(self):
        first = self._socket(self.first)
        self.second.match_chat_enabled = False
        db.session.commit()
        first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        context = self._event(first, 'hybrid_chat_context')[0]['args'][0]
        self.assertFalse(context['available'])
        self.assertEqual(context['reason'], 'chat_preference_required')

        self.second.match_chat_enabled = True
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

    def test_chat_defaults_on_without_discovery_profiles(self):
        DiscoveryProfile.query.delete()
        self.room.player1_profile_visible = False
        self.room.player2_profile_visible = False
        db.session.commit()
        for user in (self.first, self.second):
            client = self._socket(user)
            client.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
            context = self._event(client, 'hybrid_chat_context')[0]['args'][0]
            self.assertTrue(context['available'])

    def test_inactive_opponent_fails_closed(self):
        first = self._socket(self.first)
        self.second.is_active = False
        db.session.commit()
        first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
        inactive = self._event(first, 'hybrid_chat_context')[0]['args'][0]
        self.assertFalse(inactive['available'])
        self.assertEqual(inactive['reason'], 'opponent_unavailable')

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

    def test_authorization_failure_is_fail_closed_without_ending_game_session(self):
        first = self._socket(self.first)

        with patch(
            'hybrid.chat._authorized_chat_context',
            side_effect=RuntimeError('authorization dependency offline'),
        ):
            first.emit('hybrid_chat_context', {'room_code': 'CHATROOM'})
            context = self._event(first, 'hybrid_chat_context')[0]['args'][0]
            self.assertFalse(context['available'])
            self.assertEqual(context['reason'], 'authorization_unavailable')
            self.assertTrue(first.is_connected())

            first.emit('hybrid_chat_send', {
                'room_code': 'CHATROOM',
                'message': 'Gameplay must continue',
                'client_message_id': 'authfail_12345678',
            })
            error = self._event(first, 'hybrid_chat_error')[0]['args'][0]
            self.assertEqual(error['code'], 'authorization_unavailable')

        self.assertTrue(first.is_connected())
        self.assertEqual(db.session.get(GameRoom, self.room.id).status, 'in_progress')


if __name__ == '__main__':
    unittest.main()
