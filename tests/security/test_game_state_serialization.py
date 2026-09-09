import json
import pickle
import unittest
import uuid
from unittest.mock import patch

from game.manager_redis import GAME_KEY_PREFIX, GameManager
from game.state_codec import (
    GameStateCodecError,
    decode_session,
    encode_session,
    session_to_document,
)


_PICKLE_TRIPWIRE = False


def _trip_pickle_loader():
    global _PICKLE_TRIPWIRE
    _PICKLE_TRIPWIRE = True
    return {}


class _ExecutablePickle:
    def __reduce__(self):
        return (_trip_pickle_loader, ())


class FakeRedis:
    def __init__(self, ping_error=None):
        self.values = {}
        self.expiries = {}
        self.ping_error = ping_error

    def ping(self):
        if self.ping_error:
            raise self.ping_error
        return True

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.expiries[key] = int(ttl)
        return True

    def delete(self, key):
        self.expiries.pop(key, None)
        return int(self.values.pop(key, None) is not None)

    def scan_iter(self, match=None, count=None):
        prefix = str(match or '').rstrip('*')
        for key in list(self.values):
            if str(key).startswith(prefix):
                yield key


class SafeGameStateSerializationTests(unittest.TestCase):
    def setUp(self):
        global _PICKLE_TRIPWIRE
        _PICKLE_TRIPWIRE = False
        self.redis = FakeRedis()
        self.manager = GameManager(
            redis_client=self.redis,
            security_mode='monitor',
            ttl_seconds=900,
            max_payload_bytes=262144,
            local_environment=True,
        )

    def test_create_uses_versioned_json_namespace_and_ttl(self):
        game_id, original = self.manager.create_game('local', card_count=6)
        key = f'{GAME_KEY_PREFIX}{game_id}'
        payload = self.redis.values[key]
        document = json.loads(payload.decode('utf-8'))

        self.assertEqual(document['schema'], 'umshova.game-session')
        self.assertEqual(document['version'], 1)
        self.assertEqual(document['session']['mode'], 'local')
        self.assertEqual(self.redis.expiries[key], 900)
        self.assertNotIn(b'pickle', payload.lower())
        self.assertEqual(
            [len(player.hand) for player in original['engine'].players], [6, 6]
        )

    def test_round_trip_preserves_complete_mutable_game_state(self):
        game_id, _ = self.manager.create_game('local', card_count=8)
        engine = self.manager.get_game(game_id)
        attack_index = next((
            index for index, card in enumerate(engine.players[0].hand)
            if card.value >= 4
        ), None)
        if attack_index is None:
            deck_index = next(
                index for index, card in enumerate(engine.deck.cards)
                if card.value >= 4
            )
            engine.players[0].hand.append(engine.deck.cards.pop(deck_index))
            attack_index = len(engine.players[0].hand) - 1
        attacked = engine.players[0].hand[attack_index]
        result = engine.attack(0, attack_index)
        engine.state.trail_value = 2
        engine.state.defence_cards = ['A♥', '3♣']
        engine.state.defender_drawn_card = 'K♠'
        self.manager.update_game(game_id, engine)

        second_worker = GameManager(
            redis_client=self.redis,
            security_mode='monitor',
            ttl_seconds=900,
            max_payload_bytes=262144,
            local_environment=True,
        )
        restored = second_worker.get_game(game_id)

        self.assertTrue(result['ok'])
        self.assertEqual(restored.state.phase, 'DEFENSE')
        self.assertEqual(str(restored.state.attack_card), str(attacked))
        self.assertEqual(restored.state.trail_value, 2)
        self.assertEqual(restored.state.defence_cards, ['A♥', '3♣'])
        self.assertEqual(restored.state.defender_drawn_card, 'K♠')
        self.assertEqual(restored.get_state(), engine.get_state())
        self.assertEqual(
            [str(card) for card in restored.deck.cards],
            [str(card) for card in engine.deck.cards],
        )

    def test_safe_namespace_rejects_executable_pickle_without_running_it(self):
        game_id = str(uuid.uuid4())
        self.redis.values[f'{GAME_KEY_PREFIX}{game_id}'] = pickle.dumps(
            _ExecutablePickle()
        )

        with self.assertRaises(KeyError):
            self.manager.get_game(game_id)

        self.assertFalse(_PICKLE_TRIPWIRE)
        self.assertEqual(
            self.manager.codec_counts['game_state_payload_rejected'], 1
        )

    def test_legacy_namespace_is_detected_but_never_deserialized(self):
        game_id = str(uuid.uuid4())
        self.redis.values[f'game:{game_id}'] = pickle.dumps(_ExecutablePickle())

        with self.assertRaises(KeyError):
            self.manager.get_game(game_id)

        self.assertFalse(_PICKLE_TRIPWIRE)
        self.assertEqual(
            self.manager.codec_counts['game_state_legacy_payload_rejected'], 1
        )

    def test_monitor_rejection_uses_privacy_safe_structured_audit_fields(self):
        game_id = str(uuid.uuid4())
        self.redis.values[f'{GAME_KEY_PREFIX}{game_id}'] = b'not-json'

        with patch('security.audit_security_event') as audit:
            with self.assertRaises(KeyError):
                self.manager.get_game(game_id)

        audit.assert_called_once_with(
            'game_state_payload_rejected',
            category='redis_game_state',
            outcome='rejected',
            details={'reason': 'invalid_json'},
        )

    def test_unknown_version_unknown_fields_and_duplicate_keys_fail_closed(self):
        _, session = self.manager.create_game('human_vs_ai', card_count=6)
        document = session_to_document(session)
        document['version'] = 2
        with self.assertRaisesRegex(GameStateCodecError, 'unsupported_version'):
            decode_session(json.dumps(document).encode('utf-8'))

        document['version'] = 1
        document['session']['unexpected'] = True
        with self.assertRaisesRegex(GameStateCodecError, 'invalid_session'):
            decode_session(json.dumps(document).encode('utf-8'))

        with self.assertRaisesRegex(GameStateCodecError, 'duplicate_json_key'):
            decode_session(b'{"schema":"x","schema":"y"}')

    def test_oversized_payload_is_rejected_before_json_parsing(self):
        with self.assertRaisesRegex(GameStateCodecError, 'payload_too_large'):
            decode_session(b'{' + (b'x' * 128), max_payload_bytes=32)

    def test_invalid_active_card_duplication_is_rejected(self):
        _, session = self.manager.create_game('local', card_count=6)
        document = session_to_document(session)
        duplicate = dict(document['session']['engine']['players'][0]['hand'][0])
        document['session']['engine']['players'][1]['hand'][0] = duplicate

        with self.assertRaisesRegex(GameStateCodecError, 'duplicate_active_card'):
            decode_session(json.dumps(document).encode('utf-8'))

    def test_list_games_scans_only_safe_namespace(self):
        game_id, _ = self.manager.create_game('local', card_count=10)
        self.redis.values[f'game:{uuid.uuid4()}'] = b'legacy'

        games = self.manager.list_games()

        self.assertEqual(set(games), {game_id})
        self.assertEqual(games[game_id]['mode'], 'local')

    def test_off_mode_still_uses_safe_json(self):
        manager = GameManager(
            redis_client=self.redis,
            security_mode='off',
            local_environment=True,
        )
        game_id, _ = manager.create_game('local', card_count=6)

        self.assertTrue(self.redis.values[f'{GAME_KEY_PREFIX}{game_id}'].startswith(b'{'))

    def test_non_local_enforce_mode_requires_redis(self):
        with self.assertRaisesRegex(RuntimeError, 'required in enforce mode'):
            GameManager(
                redis_client=FakeRedis(ConnectionError('unavailable')),
                security_mode='enforce',
                local_environment=False,
            )

    def test_monitor_mode_keeps_local_memory_fallback(self):
        manager = GameManager(
            redis_client=FakeRedis(ConnectionError('unavailable')),
            security_mode='monitor',
            local_environment=True,
        )

        game_id, _ = manager.create_game('local', card_count=6)

        self.assertFalse(manager.use_redis)
        self.assertEqual(len(manager.get_game(game_id).players), 2)

    def test_encoder_and_decoder_enforce_payload_limit(self):
        _, session = self.manager.create_game('local', card_count=6)
        with self.assertRaisesRegex(GameStateCodecError, 'payload_too_large'):
            encode_session(session, max_payload_bytes=32)


if __name__ == '__main__':
    unittest.main()
