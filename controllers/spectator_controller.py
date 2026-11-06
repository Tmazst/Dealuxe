"""Guest-accessible, read-only tournament spectating."""
from flask import Blueprint, abort, current_app, jsonify, render_template, session
from flask_socketio import emit, join_room, leave_room, rooms
from database import GameRoom
from services.spectator_service import get_public_snapshot, public_match, spectator_channel

spectator_bp = Blueprint('spectator', __name__)


def _find_public_room(code):
    if not isinstance(code, str) or not code or len(code) > 16:
        return None
    room = GameRoom.query.filter_by(room_code=code).first()
    if not room or room.status not in {'in_progress', 'paused', 'completed'} or public_match(room) is None:
        return None
    return room


@spectator_bp.get('/watch/<room_code>')
def watch_game(room_code):
    room = _find_public_room(room_code)
    if room is None:
        abort(404)
    response = current_app.make_response(render_template(
        'watch_game.html', room_code=room.room_code,
        bracket_url=f'/tournaments/{room.tournament_id}/bracket',
        is_guest=not session.get('user_id'),
    ))
    response.headers['Cache-Control'] = 'no-store'
    return response


@spectator_bp.get('/api/watch/<room_code>')
def watch_state(room_code):
    room = _find_public_room(room_code)
    if room is None:
        return jsonify({'error': 'This game is not available to watch'}), 404
    try:
        payload = get_public_snapshot(room, current_app.extensions['game_manager'])
    except Exception:
        current_app.logger.exception('Spectator state unavailable room_id=%s', room.id)
        return jsonify({'error': 'Live updates are temporarily unavailable'}), 503
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response


# Reuse the existing configurable event budget for these read-only snapshots.
watch_state._rate_limit_category = 'socket_event'


def init_spectator_events(socketio, manager):
    @socketio.on('watch_game')
    def watch(data=None):
        code = data.get('room_code') if isinstance(data, dict) else None
        room = _find_public_room(code)
        if room is None:
            emit('spectator_error', {'message': 'This game is not available to watch'})
            return {'ok': False}
        # Each socket can watch one match, without joining any player room.
        for name in list(rooms()):
            if name.startswith('spectator:'):
                leave_room(name)
        channel = spectator_channel(room.room_code)
        join_room(channel)
        try:
            emit('spectator_update', get_public_snapshot(room, manager))
        except Exception:
            leave_room(channel)
            emit('spectator_error', {'message': 'Live updates are temporarily unavailable'})
            return {'ok': False}
        return {'ok': True}

    @socketio.on('leave_watch_game')
    def leave_watch(data=None):
        for name in list(rooms()):
            if name.startswith('spectator:'):
                leave_room(name)
        return {'ok': True}
