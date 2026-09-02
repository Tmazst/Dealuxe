"""Focused Version 3 MVP load and concurrency acceptance tests.

Run only with ``DEALUXE_DATABASE_URI`` bound to a disposable database before
``app`` is imported.  The repository-level drop guard remains the final safety
boundary if that isolation is ever missed.
"""

from concurrent.futures import ThreadPoolExecutor
import math
import os
import time
import unittest

os.environ['ENV'] = 'development'

from app import app, socketio
from database import (
    DiscoveryProfile,
    GameRoom,
    HybridPilotMetric,
    User,
    UserBlock,
    db,
)
from hybrid.chat import MemoryChatStore
from hybrid.matching import MatchingPolicy, ParticipantSnapshot, match_first_round


def _percentile(values, percentile):
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return ordered[index]


def _matching_profile(user_id, intent):
    return ParticipantSnapshot(
        user_id=user_id,
        profile_enabled=True,
        entitlement_active=True,
        is_visible=True,
        moderation_status='not_required',
        intent=intent,
        category='services',
        subcategory='repairs',
        location='manzini',
    )


class TestHybridMatcherLoad(unittest.TestCase):
    def test_four_concurrent_maximum_brackets_represent_sixty_four_players(self):
        brackets = []
        for bracket_number in range(4):
            start = (bracket_number * 16) + 1
            brackets.append(tuple(
                _matching_profile(
                    user_id,
                    'selling' if user_id % 2 else 'seeking',
                )
                for user_id in range(start, start + 16)
            ))

        def run_matcher(index):
            started = time.perf_counter()
            result = match_first_round(
                brackets[index],
                'v3-0906c-bracket-{0}'.format(index),
                MatchingPolicy(timeout_ms=500),
            )
            return result, (time.perf_counter() - started) * 1000

        with ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(run_matcher, range(4)))

        elapsed = [item[1] for item in outcomes]
        for result, _duration in outcomes:
            self.assertIn(result.status, ('matched', 'no_positive_match', 'timeout'))
            if result.status != 'timeout':
                self.assertEqual(len(result.seed_order), 16)
                self.assertEqual(len(set(result.seed_order)), 16)
        p95_ms = _percentile(elapsed, 95)
        print(
            '[V3-0906C] concurrent matching: 64 players, '
            '4 brackets, p95={0:.3f} ms, max={1:.3f} ms'.format(
                p95_ms, max(elapsed)
            )
        )
        self.assertLess(p95_ms, 750)


class TestHybridRoomConcurrency(unittest.TestCase):
    ROOM_COUNT = 32

    @classmethod
    def setUpClass(cls):
        cls.original_config = {
            key: app.config.get(key) for key in (
                'TESTING', 'HYBRID_ENABLED', 'HYBRID_PROFILE_ENABLED',
                'HYBRID_CHAT_ENABLED', 'WTF_CSRF_ENABLED',
            )
        }
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
            HYBRID_CHAT_ENABLED=True,
        )
        cls.context = app.app_context()
        cls.context.push()
        db.drop_all()
        db.create_all()

        cls.users = []
        for number in range(cls.ROOM_COUNT * 2):
            user = User(
                username='load-user-{0:02d}'.format(number),
                email='load-user-{0:02d}@test.com'.format(number),
            )
            user.set_password('pw')
            cls.users.append(user)
        db.session.add_all(cls.users)
        db.session.flush()

        cls.rooms = []
        for room_number in range(cls.ROOM_COUNT):
            first = cls.users[room_number * 2]
            second = cls.users[(room_number * 2) + 1]
            db.session.add_all([
                DiscoveryProfile(
                    user_id=first.id,
                    is_enabled=True,
                    is_visible=True,
                    chat_preference_enabled=True,
                    intent='seeking',
                    category='services',
                    subcategory='repairs',
                    location='Manzini',
                    predefined_caption='seeking_services',
                    moderation_status='not_required',
                ),
                DiscoveryProfile(
                    user_id=second.id,
                    is_enabled=True,
                    is_visible=True,
                    chat_preference_enabled=True,
                    intent='selling',
                    category='services',
                    subcategory='repairs',
                    location='Manzini',
                    predefined_caption='offering_services',
                    moderation_status='not_required',
                ),
            ])
            room = GameRoom(
                room_code='LOAD{0:04d}'.format(room_number),
                player1_id=first.id,
                player2_id=second.id,
                status='in_progress',
            )
            cls.rooms.append(room)
            db.session.add(room)
        db.session.commit()
        cls.user_ids = [user.id for user in cls.users]
        cls.usernames = [user.username for user in cls.users]
        cls.user_emails = [user.email for user in cls.users]
        cls.room_ids = [room.id for room in cls.rooms]
        cls.room_codes = [room.room_code for room in cls.rooms]

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.context.pop()
        app.config.update(cls.original_config)

    @staticmethod
    def _authenticated_http_client(user_id):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = user_id
            session['username'] = 'load-user'
        return client

    @classmethod
    def _context_request(cls, room_number, seat):
        user_index = (room_number * 2) + seat
        user_id = cls.user_ids[user_index]
        started = time.perf_counter()
        response = cls._authenticated_http_client(user_id).get(
            '/api/hybrid/game/{0}/context'.format(cls.room_codes[room_number])
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        return room_number, seat, response.status_code, response.get_json(), elapsed_ms

    def setUp(self):
        GameRoom.query.update({
            GameRoom.player1_profile_visible: True,
            GameRoom.player2_profile_visible: True,
        })
        UserBlock.query.delete()
        HybridPilotMetric.query.delete()
        db.session.commit()
        app.extensions['hybrid_chat_store'] = MemoryChatStore()

    def test_sixty_four_concurrent_context_reads_are_room_scoped(self):
        requests = [
            (room_number, seat)
            for room_number in range(self.ROOM_COUNT)
            for seat in (0, 1)
        ]
        with ThreadPoolExecutor(max_workers=16) as executor:
            outcomes = list(executor.map(
                lambda item: self._context_request(*item), requests
            ))

        elapsed = []
        for room_number, seat, status, payload, elapsed_ms in outcomes:
            self.assertEqual(status, 200)
            context = payload['context']
            self.assertTrue(context['available'])
            opponent_index = (room_number * 2) + (1 - seat)
            self.assertEqual(
                context['opponent']['username'], self.usernames[opponent_index]
            )
            self.assertEqual(
                context['opponent']['email'], self.user_emails[opponent_index]
            )
            body = str(payload)
            other_room = (room_number + 1) % self.ROOM_COUNT
            self.assertNotIn(self.user_emails[other_room * 2], body)
            self.assertNotIn(self.user_emails[(other_room * 2) + 1], body)
            elapsed.append(elapsed_ms)

        p95_ms = _percentile(elapsed, 95)
        print(
            '[V3-0906C] profile context: 64 concurrent reads, '
            'p95={0:.3f} ms, max={1:.3f} ms'.format(p95_ms, max(elapsed))
        )
        self.assertLess(p95_ms, 1500)

    def test_concurrent_hide_unhide_and_blocks_remain_reciprocal(self):
        room_numbers = range(8)

        def set_visible(room_number, seat, visible):
            user_id = self.user_ids[(room_number * 2) + seat]
            response = self._authenticated_http_client(user_id).put(
                '/api/hybrid/game/{0}/preferences'.format(
                    self.room_codes[room_number]
                ),
                json={'profile_visible': visible},
            )
            return response.status_code

        hide_actions = [
            (room_number, seat, False)
            for room_number in room_numbers
            for seat in (0, 1)
        ]
        with ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(
                lambda item: set_visible(*item), hide_actions
            ))
        self.assertEqual(statuses, [200] * len(hide_actions))

        db.session.expire_all()
        for room_number in room_numbers:
            room = db.session.get(GameRoom, self.room_ids[room_number])
            self.assertFalse(room.player1_profile_visible)
            self.assertFalse(room.player2_profile_visible)

        unhide_actions = [
            (room_number, seat, True)
            for room_number in room_numbers
            for seat in (0, 1)
        ]
        with ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(
                lambda item: set_visible(*item), unhide_actions
            ))
        self.assertEqual(statuses, [200] * len(unhide_actions))

        def create_block(room_number):
            blocker_id = self.user_ids[room_number * 2]
            blocked_id = self.user_ids[(room_number * 2) + 1]
            response = self._authenticated_http_client(blocker_id).post(
                '/api/hybrid/blocks', json={'blocked_user_id': blocked_id}
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=8) as executor:
            block_statuses = list(executor.map(create_block, room_numbers))
        self.assertEqual(block_statuses, [201] * len(block_statuses))

        for room_number in room_numbers:
            for seat in (0, 1):
                _room, _seat, status, payload, _elapsed = self._context_request(
                    room_number, seat
                )
                self.assertEqual(status, 200)
                self.assertFalse(payload['context']['available'])
                self.assertEqual(payload['context']['reason'], 'blocked')

    def test_sixteen_simultaneous_chats_do_not_cross_rooms(self):
        room_count = 16
        socket_pairs = []
        try:
            for room_number in range(room_count):
                pair = []
                for seat in (0, 1):
                    user_id = self.user_ids[(room_number * 2) + seat]
                    http = self._authenticated_http_client(user_id)
                    client = socketio.test_client(app, flask_test_client=http)
                    self.assertTrue(client.is_connected())
                    client.get_received()
                    pair.append(client)
                socket_pairs.append(pair)

            def send_message(room_number):
                sender = socket_pairs[room_number][0]
                sender.emit('hybrid_chat_send', {
                    'room_code': self.room_codes[room_number],
                    'message': 'private-room-{0:02d}'.format(room_number),
                    'client_message_id': 'load_{0:02d}_message'.format(room_number),
                })

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=16) as executor:
                list(executor.map(send_message, range(room_count)))
            elapsed_ms = (time.perf_counter() - started) * 1000

            for room_number, (sender, receiver) in enumerate(socket_pairs):
                expected = 'private-room-{0:02d}'.format(room_number)
                sender_messages = [
                    event['args'][0] for event in sender.get_received()
                    if event['name'] == 'hybrid_chat_message'
                ]
                receiver_messages = [
                    event['args'][0] for event in receiver.get_received()
                    if event['name'] == 'hybrid_chat_message'
                ]
                self.assertEqual(len(sender_messages), 1)
                self.assertEqual(len(receiver_messages), 1)
                self.assertEqual(sender_messages[0]['message'], expected)
                self.assertEqual(receiver_messages[0]['message'], expected)
                self.assertEqual(sender_messages[0]['sender'], 'you')
                self.assertEqual(receiver_messages[0]['sender'], 'opponent')

            delivered = HybridPilotMetric.query.filter_by(
                metric_key='chat_messages_delivered'
            ).one()
            self.assertEqual(delivered.total_count, room_count)

            print(
                '[V3-0906C] Q-messanger: 16 simultaneous isolated sends, '
                'batch={0:.3f} ms'.format(elapsed_ms)
            )
            self.assertLess(elapsed_ms, 3000)
        finally:
            for pair in socket_pairs:
                for client in pair:
                    if client.is_connected():
                        client.disconnect()


if __name__ == '__main__':
    unittest.main()
