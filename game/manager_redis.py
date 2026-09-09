"""Redis-backed game manager using an allowlisted, versioned JSON schema."""

from collections import Counter
import os
import time
import uuid

import redis

from game.engine import CardGameEngine
from game.models import Player
from game.state_codec import (
    DEFAULT_MAX_PAYLOAD_BYTES,
    GameStateCodecError,
    decode_session,
    encode_session,
)


GAME_KEY_PREFIX = 'umshova:game:v1:'
LEGACY_GAME_KEY_PREFIX = 'game:'
DEFAULT_TTL_SECONDS = 24 * 60 * 60
SECURITY_MODES = {'off', 'monitor', 'enforce'}


class GameManager:
    """Store game sessions in Redis, with a local in-memory fallback.

    ``off`` disables codec audit events only; safe JSON remains mandatory.
    ``monitor`` is the pilot default and records rejected/legacy payloads.
    ``enforce`` additionally refuses non-local startup when Redis is down.
    No mode permits pickle or another executable object format.
    """

    def __init__(
        self,
        redis_url=None,
        security_mode='monitor',
        ttl_seconds=DEFAULT_TTL_SECONDS,
        max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES,
        local_environment=True,
        redis_client=None,
    ):
        self.security_mode = str(security_mode or '').strip().lower()
        if self.security_mode not in SECURITY_MODES:
            raise ValueError('Invalid Redis game-state security mode')
        self.ttl_seconds = int(ttl_seconds)
        self.max_payload_bytes = int(max_payload_bytes)
        if self.ttl_seconds <= 0 or self.max_payload_bytes <= 0:
            raise ValueError('Redis game-state limits must be positive')
        self.local_environment = bool(local_environment)
        self.codec_counts = Counter()
        self.redis_client = None

        try:
            configured_url = redis_url or os.getenv(
                'REDIS_URL', 'redis://127.0.0.1:6379/0'
            )
            self.redis_client = redis_client or redis.Redis.from_url(
                configured_url,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self.redis_client.ping()
            self.use_redis = True
            print('[MANAGER] Connected to configured Redis service (safe schema v1)')
        except Exception as exc:
            if self.security_mode == 'enforce' and not self.local_environment:
                raise RuntimeError(
                    'Redis game-state storage is required in enforce mode'
                ) from exc
            print(
                f'[MANAGER] Redis connection failed ({type(exc).__name__}). '
                'Using in-memory storage.'
            )
            self.use_redis = False
            self.games = {}

    @staticmethod
    def _game_id(value):
        try:
            normalized = str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise KeyError('Game not found')
        if normalized != str(value).lower():
            raise KeyError('Game not found')
        return normalized

    @classmethod
    def _key(cls, game_id):
        return f'{GAME_KEY_PREFIX}{cls._game_id(game_id)}'

    @classmethod
    def _legacy_key(cls, game_id):
        return f'{LEGACY_GAME_KEY_PREFIX}{cls._game_id(game_id)}'

    def _audit(self, event, reason, outcome='rejected'):
        self.codec_counts[event] += 1
        if self.security_mode == 'off':
            return
        try:
            from security import audit_security_event
            audit_security_event(
                event,
                category='redis_game_state',
                outcome=outcome,
                details={'reason': str(reason)},
            )
        except Exception:
            pass

    def _encode(self, session_data):
        try:
            result = encode_session(session_data, self.max_payload_bytes)
            self.codec_counts['encoded'] += 1
            return result
        except GameStateCodecError as exc:
            self._audit('game_state_encode_rejected', exc.code)
            raise

    def _decode(self, payload):
        try:
            result = decode_session(payload, self.max_payload_bytes)
            self.codec_counts['decoded'] += 1
            return result
        except GameStateCodecError as exc:
            self._audit('game_state_payload_rejected', exc.code)
            raise

    def _read_redis_session(self, game_id):
        payload = self.redis_client.get(self._key(game_id))
        if payload is None:
            # Detect the former namespace without ever opening its value.
            if self.redis_client.get(self._legacy_key(game_id)) is not None:
                self._audit('game_state_legacy_payload_rejected', 'legacy_namespace')
            raise KeyError('Game not found')
        try:
            return self._decode(payload)
        except GameStateCodecError:
            raise KeyError('Game not found')

    def create_game(self, mode='human_vs_ai', card_count=6):
        game_id = str(uuid.uuid4())
        if mode == 'human_vs_ai':
            players = [Player('Human'), Player('Computer')]
        elif mode == 'local':
            players = [Player('Player 1'), Player('Player 2')]
        else:
            raise ValueError(f'Unsupported game mode: {mode}')

        engine = CardGameEngine(players, cards_per_player=card_count)
        session_data = {
            'engine': engine,
            'mode': mode,
            'created_at': time.time(),
            'status': 'active',
            'players': players,
            'card_count': card_count,
        }
        if self.use_redis:
            payload = self._encode(session_data)
            self.redis_client.setex(self._key(game_id), self.ttl_seconds, payload)
            print(f'[MANAGER] Created game {game_id} in Redis ({mode}, schema v1)')
        else:
            self.games[game_id] = session_data
            print(f'[MANAGER] Created game {game_id} in memory ({mode})')
        return game_id, session_data

    def get_game(self, game_id):
        if self.use_redis:
            return self._read_redis_session(game_id)['engine']
        session = self.games.get(self._game_id(game_id))
        if not session:
            raise KeyError('Game not found')
        return session['engine']

    def update_game(self, game_id, engine):
        if not isinstance(engine, CardGameEngine):
            raise ValueError('Invalid game engine')
        if self.use_redis:
            session_data = self._read_redis_session(game_id)
            session_data['engine'] = engine
            session_data['players'] = engine.players
            payload = self._encode(session_data)
            self.redis_client.setex(self._key(game_id), self.ttl_seconds, payload)
            return True
        normalized = self._game_id(game_id)
        if normalized not in self.games:
            raise KeyError('Game not found')
        self.games[normalized]['engine'] = engine
        self.games[normalized]['players'] = engine.players
        return True

    def delete_game(self, game_id):
        normalized = self._game_id(game_id)
        if self.use_redis:
            self.redis_client.delete(self._key(normalized))
            print(f'[MANAGER] Deleted game {normalized} from Redis')
        elif normalized in self.games:
            del self.games[normalized]
            print(f'[MANAGER] Deleted game {normalized} from memory')

    def list_games(self):
        if not self.use_redis:
            return {
                gid: {
                    'mode': data['mode'],
                    'status': data['status'],
                    'age': max(0.0, time.time() - data['created_at']),
                }
                for gid, data in self.games.items()
            }
        games = {}
        for key in self.redis_client.scan_iter(match=f'{GAME_KEY_PREFIX}*', count=100):
            key_text = key.decode('utf-8') if isinstance(key, bytes) else str(key)
            game_id = key_text[len(GAME_KEY_PREFIX):]
            try:
                normalized = self._game_id(game_id)
                data = self._read_redis_session(normalized)
            except KeyError:
                continue
            games[normalized] = {
                'mode': data['mode'],
                'status': data['status'],
                'age': max(0.0, time.time() - data['created_at']),
            }
        return games
