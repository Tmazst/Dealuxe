"""Private, bounded and expiring Q-messànger chat storage and events."""

import json
import re
import threading
import time
import uuid
from abc import ABCMeta, abstractmethod

from flask import session
from flask_socketio import emit

from database import DiscoveryProfile, GameRoom, User, db
from hybrid.service import users_are_blocked
from hybrid.metrics import increment_pilot_counter


CHAT_TTL_SECONDS = 24 * 60 * 60
CHAT_HISTORY_LIMIT = 10
CHAT_MESSAGE_MAX_LENGTH = 280
CHAT_RATE_LIMIT = 5
CHAT_RATE_WINDOW_SECONDS = 10
_CONTROL_CHARACTERS = re.compile(r'[\x00-\x1f\x7f-\x9f]')


class ChatStore(object, metaclass=ABCMeta):
    """Storage contract shared by Redis and the local development fallback."""

    @abstractmethod
    def add(self, room_code, message):
        raise NotImplementedError

    @abstractmethod
    def latest(self, room_code):
        raise NotImplementedError

    @abstractmethod
    def claim_message(self, room_code, user_id, client_message_id):
        raise NotImplementedError

    @abstractmethod
    def allow_send(self, room_code, user_id):
        raise NotImplementedError


class MemoryChatStore(ChatStore):
    """Thread-safe TTL fallback for local development and isolated tests."""

    def __init__(self, ttl_seconds=CHAT_TTL_SECONDS, clock=None):
        self.ttl_seconds = int(ttl_seconds)
        self.clock = clock or time.time
        self._messages = {}
        self._claims = {}
        self._rates = {}
        self._lock = threading.RLock()

    def _purge(self, now):
        cutoff = now - self.ttl_seconds
        for room_code, messages in list(self._messages.items()):
            current = [item for item in messages if item['stored_at'] > cutoff]
            if current:
                self._messages[room_code] = current
            else:
                self._messages.pop(room_code, None)
        self._claims = {
            key: expiry for key, expiry in self._claims.items() if expiry > now
        }
        rate_cutoff = now - CHAT_RATE_WINDOW_SECONDS
        for key, timestamps in list(self._rates.items()):
            current = [value for value in timestamps if value > rate_cutoff]
            if current:
                self._rates[key] = current
            else:
                self._rates.pop(key, None)

    def add(self, room_code, message):
        now = self.clock()
        stored = dict(message)
        stored['stored_at'] = now
        with self._lock:
            self._purge(now)
            messages = self._messages.setdefault(room_code, [])
            messages.append(stored)
            del messages[:-CHAT_HISTORY_LIMIT]
        return dict(message)

    def latest(self, room_code):
        now = self.clock()
        with self._lock:
            self._purge(now)
            messages = self._messages.get(room_code, [])
            if not messages:
                return None
            result = dict(messages[-1])
            result.pop('stored_at', None)
            return result

    def claim_message(self, room_code, user_id, client_message_id):
        now = self.clock()
        key = (room_code, int(user_id), client_message_id)
        with self._lock:
            self._purge(now)
            if key in self._claims:
                return False
            self._claims[key] = now + self.ttl_seconds
            return True

    def allow_send(self, room_code, user_id):
        now = self.clock()
        key = (room_code, int(user_id))
        with self._lock:
            self._purge(now)
            timestamps = self._rates.setdefault(key, [])
            if len(timestamps) >= CHAT_RATE_LIMIT:
                return False
            timestamps.append(now)
            return True


class RedisChatStore(ChatStore):
    """Redis implementation using namespaced, expiring, bounded keys."""

    def __init__(self, redis_client, ttl_seconds=CHAT_TTL_SECONDS):
        self.redis = redis_client
        self.ttl_seconds = int(ttl_seconds)

    @staticmethod
    def _room_key(room_code):
        return 'hybrid:chat:room:{0}:messages'.format(room_code)

    def add(self, room_code, message):
        key = self._room_key(room_code)
        encoded = json.dumps(message, separators=(',', ':'))
        pipeline = self.redis.pipeline()
        pipeline.rpush(key, encoded)
        pipeline.ltrim(key, -CHAT_HISTORY_LIMIT, -1)
        pipeline.expire(key, self.ttl_seconds)
        pipeline.execute()
        return dict(message)

    def latest(self, room_code):
        value = self.redis.lindex(self._room_key(room_code), -1)
        if not value:
            return None
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return json.loads(value)

    def claim_message(self, room_code, user_id, client_message_id):
        key = 'hybrid:chat:replay:{0}:{1}:{2}'.format(
            room_code, user_id, client_message_id
        )
        return bool(self.redis.set(key, '1', nx=True, ex=self.ttl_seconds))

    def allow_send(self, room_code, user_id):
        key = 'hybrid:chat:rate:{0}:{1}'.format(room_code, user_id)
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, CHAT_RATE_WINDOW_SECONDS)
        return count <= CHAT_RATE_LIMIT


def build_chat_store(game_manager):
    """Reuse the verified Redis client or use the local in-memory fallback."""
    if getattr(game_manager, 'use_redis', False):
        return RedisChatStore(game_manager.redis_client)
    return MemoryChatStore()


def _chat_error(code, message):
    emit('hybrid_chat_error', {'code': code, 'message': message})


def _authorized_chat_context(app, user_id, room_code):
    if not (
        app.config.get('HYBRID_ENABLED')
        and app.config.get('HYBRID_PROFILE_ENABLED')
        and app.config.get('HYBRID_CHAT_ENABLED')
    ):
        raise PermissionError('chat_disabled')
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        raise PermissionError('account_inactive')
    room = GameRoom.query.filter_by(room_code=str(room_code or '').strip()).first()
    if room is None:
        raise LookupError('room_not_found')
    if not room.is_player_in_room(user_id):
        raise PermissionError('not_room_member')
    if room.status not in ('in_progress', 'paused'):
        raise PermissionError('room_inactive')
    opponent_id = room.get_opponent_id(user_id)
    if not opponent_id:
        raise PermissionError('opponent_unavailable')
    opponent = db.session.get(User, opponent_id)
    if not opponent or not opponent.is_active:
        raise PermissionError('opponent_unavailable')
    if users_are_blocked(user_id, opponent_id):
        raise PermissionError('blocked')

    profiles = {
        profile.user_id: profile
        for profile in DiscoveryProfile.query.filter(
            DiscoveryProfile.user_id.in_((user_id, opponent_id))
        ).all()
    }
    own_profile = profiles.get(user_id)
    opponent_profile = profiles.get(opponent_id)
    if not own_profile or not opponent_profile:
        raise PermissionError('chat_preference_required')
    if not (
        own_profile.is_enabled and own_profile.is_visible
        and opponent_profile.is_enabled and opponent_profile.is_visible
        and own_profile.chat_preference_enabled
        and opponent_profile.chat_preference_enabled
    ):
        raise PermissionError('chat_preference_required')
    if (
        own_profile.custom_caption
        and own_profile.moderation_status != 'approved'
    ) or (
        opponent_profile.custom_caption
        and opponent_profile.moderation_status != 'approved'
    ):
        raise PermissionError('caption_review_required')
    own_room_visible = (
        room.player1_profile_visible if user_id == room.player1_id
        else room.player2_profile_visible
    )
    opponent_room_visible = (
        room.player1_profile_visible if opponent_id == room.player1_id
        else room.player2_profile_visible
    )
    if not own_room_visible or not opponent_room_visible:
        raise PermissionError('hidden_for_game')
    return room, opponent_id


def _validate_payload(data):
    if not isinstance(data, dict):
        raise ValueError('invalid_payload')
    if set(data) != {'room_code', 'message', 'client_message_id'}:
        raise ValueError('invalid_payload')
    room_code = str(data.get('room_code') or '').strip()
    message = data.get('message')
    client_message_id = str(data.get('client_message_id') or '').strip()
    if not room_code or not isinstance(message, str):
        raise ValueError('invalid_payload')
    message = message.strip()
    if not message or len(message) > CHAT_MESSAGE_MAX_LENGTH:
        raise ValueError('invalid_message')
    if _CONTROL_CHARACTERS.search(message):
        raise ValueError('invalid_message')
    if not re.match(r'^[A-Za-z0-9_-]{8,80}$', client_message_id):
        raise ValueError('invalid_message_id')
    return room_code, message, client_message_id


def _present_message(message, requester_id):
    if not message:
        return None
    return {
        'id': message['id'],
        'room_code': message['room_code'],
        'sender': 'you' if int(message['sender_id']) == int(requester_id) else 'opponent',
        'message': message['message'],
        'sent_at': message['sent_at'],
    }


def init_hybrid_chat_events(socketio, app):
    """Register private Socket.IO events without coupling chat to gameplay."""

    @socketio.on('hybrid_chat_context')
    def handle_chat_context(data):
        user_id = session.get('user_id')
        room_code = data.get('room_code') if isinstance(data, dict) else None
        if not user_id:
            _chat_error('not_authenticated', 'Please sign in to use Q-messànger')
            return
        try:
            _authorized_chat_context(app, user_id, room_code)
        except (LookupError, PermissionError) as exc:
            emit('hybrid_chat_context', {
                'room_code': room_code,
                'available': False,
                'reason': str(exc),
            })
            return
        except Exception:
            db.session.rollback()
            app.logger.exception(
                'Optional Q-messanger authorization failed for room %s',
                room_code,
            )
            emit('hybrid_chat_context', {
                'room_code': room_code,
                'available': False,
                'reason': 'authorization_unavailable',
            })
            return
        try:
            latest = app.extensions['hybrid_chat_store'].latest(room_code)
        except Exception:
            increment_pilot_counter('chat_storage_failures')
            _chat_error('storage_unavailable', 'Q-messànger is temporarily unavailable')
            return
        emit('hybrid_chat_context', {
            'room_code': room_code,
            'available': True,
            'latest': _present_message(latest, user_id),
        })

    @socketio.on('hybrid_chat_send')
    def handle_chat_send(data):
        user_id = session.get('user_id')
        if not user_id:
            _chat_error('not_authenticated', 'Please sign in to use Q-messànger')
            return
        try:
            room_code, message_text, client_message_id = _validate_payload(data)
            room, opponent_id = _authorized_chat_context(app, user_id, room_code)
        except ValueError as exc:
            _chat_error(str(exc), 'Message could not be sent')
            return
        except LookupError:
            _chat_error('room_not_found', 'Game room was not found')
            return
        except PermissionError as exc:
            _chat_error(str(exc), 'Q-messànger is unavailable for this game')
            return
        except Exception:
            db.session.rollback()
            app.logger.exception(
                'Optional Q-messanger authorization failed for room %s',
                data.get('room_code') if isinstance(data, dict) else None,
            )
            _chat_error(
                'authorization_unavailable',
                'Q-messànger is temporarily unavailable',
            )
            return

        store = app.extensions['hybrid_chat_store']
        try:
            if not store.claim_message(room.room_code, user_id, client_message_id):
                _chat_error('duplicate_message', 'This message was already sent')
                return
            if not store.allow_send(room.room_code, user_id):
                _chat_error('rate_limited', 'Please wait before sending another message')
                return

            message = store.add(room.room_code, {
                'id': uuid.uuid4().hex,
                'room_code': room.room_code,
                'sender_id': int(user_id),
                'message': message_text,
                'sent_at': int(time.time()),
            })
        except Exception:
            increment_pilot_counter('chat_storage_failures')
            _chat_error('storage_unavailable', 'Q-messànger is temporarily unavailable')
            return
        increment_pilot_counter('chat_messages_delivered')
        socketio.emit(
            'hybrid_chat_message', _present_message(message, user_id),
            room='user_{0}'.format(user_id),
        )
        socketio.emit(
            'hybrid_chat_message', _present_message(message, opponent_id),
            room='user_{0}'.format(opponent_id),
        )

    return socketio
