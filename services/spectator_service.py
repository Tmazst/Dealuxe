"""Public tournament views. Never copy engine dictionaries into public payloads."""
import json
import time
from collections import OrderedDict
from datetime import datetime
from threading import Lock

from flask import current_app
from redis.exceptions import WatchError
from database import Tournament, TournamentMatch, TournamentBracket, User, db

_cache = OrderedDict()
_lock = Lock()
TTL = 86400


def spectator_channel(room_code):
    return f'spectator:{room_code}'


def public_match(room):
    if not room or not room.is_tournament_game or not room.tournament_id:
        return None
    tournament = db.session.get(Tournament, room.tournament_id)
    if not tournament or tournament.status == 'cancelled':
        return None
    return TournamentMatch.query.filter_by(
        game_room_id=room.id, tournament_id=tournament.id,
    ).first()


def _key(room):
    # Include database IDs and game ID so reused room codes cannot reuse history.
    return f'umshova:spectator:v1:{room.id}:{room.game_id}'


def _redis(manager):
    return manager.redis_client if manager and manager.use_redis else None


def _read(room, manager):
    client = _redis(manager)
    if client is not None:
        raw = client.get(_key(room))
        return json.loads(raw) if raw else {}
    with _lock:
        entry = _cache.get(_key(room))
        return json.loads(entry[1]) if entry and entry[0] > time.time() else {}


def _save(room, manager, build):
    client = _redis(manager)
    if client is not None:
        for _ in range(5):
            with client.pipeline() as pipe:
                try:
                    pipe.watch(_key(room))
                    raw = pipe.get(_key(room))
                    payload = build(json.loads(raw) if raw else {})
                    pipe.multi()
                    pipe.setex(_key(room), TTL, json.dumps(payload))
                    pipe.execute()
                    return payload
                except WatchError:
                    continue
        raise RuntimeError('Spectator snapshot is busy')
    with _lock:
        entry = _cache.get(_key(room))
        prior = json.loads(entry[1]) if entry and entry[0] > time.time() else {}
        payload = build(prior)
        _cache[_key(room)] = (time.time() + TTL, json.dumps(payload))
        _cache.move_to_end(_key(room))
        while len(_cache) > 256:
            _cache.popitem(last=False)
        return payload


def _utc(value):
    return value.isoformat() + 'Z' if value else None


def masked_player_state(state, player_index=None):
    """Explicit player contract; an absent seat exposes neither hand."""
    hands = state.get('hands', {})
    payload = {key: state.get(key) for key in (
        'phase', 'attacker', 'defender', 'attack_card', 'attack_card_value',
        'game_over', 'winner',
    )}
    payload['players'] = []
    payload['hands'] = {}
    for index in range(2):
        hand = hands.get(index, hands.get(str(index), []))
        player = {'hand_count': len(hand)}
        if index == player_index:
            player['hand'] = list(hand)
            payload['hands'][index] = list(hand)
        payload['players'].append(player)
    # Engine logs are intentionally absent from this public-safe contract.
    payload['ui_log'] = []
    return payload


def action_result_data(result):
    data = result.get_json() if hasattr(result, 'get_json') else result
    if not isinstance(data, dict):
        return {}
    nested = data.get('results', data)
    return nested if isinstance(nested, dict) else {}


def public_action_result(result):
    """Failed defense responses can contain cards still in a private hand."""
    data = action_result_data(result)
    if not isinstance(data, dict) or data.get('error'):
        return None
    return {key: data[key] for key in (
        'ok', 'success', 'game_over', 'winner', 'phase', 'used_cards', 'used_count',
    ) if key in data}


def player_action_result(result, is_actor):
    """Results contain consume_ui_state(), which also includes BOTH hands."""
    safe = public_action_result(result)
    if not is_actor:
        return safe
    data = action_result_data(result)
    if data.get('error'):
        return {'error': data['error']}
    raw = result.get_json() if hasattr(result, 'get_json') else result
    safe = safe or {}
    if isinstance(raw, dict) and raw.get('defender_drawn_card'):
        safe['defender_drawn_card'] = raw['defender_drawn_card']
    return safe


def public_played_cards(result, action):
    data = action_result_data(result)
    if not isinstance(data, dict) or data.get('error'):
        return None
    if action == 'defend':
        return data.get('used_cards')
    if action == 'rule8_drop' and data.get('dropped'):
        return [data['dropped']]
    return None


def _card_value(card):
    rank = str(card).rstrip('♥♦♣♠')
    if rank in {'A', 'J', 'Q', 'K'}:
        return {'A': 1, 'J': 11, 'Q': 12, 'K': 13}[rank]
    return int(rank) if rank.isdigit() and 1 <= int(rank) <= 13 else None


def _attack_exchange(state, identity):
    if not state or not state.get('attack_card'):
        return None
    return {
        'id': identity, 'kind': 'attack',
        'attack_card': state['attack_card'],
        'target_value': state.get('attack_card_value') or _card_value(state['attack_card']),
        'attacker_index': state.get('attacker'), 'defender_index': state.get('defender'),
        'defense_cards': [], 'outcome': 'pending',
    }


def _update_exchange(payload, action, actor_index, played_cards, before_state, trail_crashed):
    exchange = payload.get('exchange')
    if action == 'attack':
        exchange = _attack_exchange(payload, payload['version'])
    elif action in {'defend', 'draw'}:
        # The first update after rollout may be a defense in an existing game.
        # Capture the attack BEFORE the engine clears it or swaps player roles.
        if (not exchange or exchange.get('outcome') != 'pending'
                or (before_state and before_state.get('attack_card')
                    and exchange.get('attack_card') != before_state['attack_card'])):
            exchange = _attack_exchange(before_state, payload['version'])
        if exchange:
            exchange = dict(exchange)
            exchange['defender_index'] = actor_index
            exchange['defense_cards'] = list(played_cards or [])[:3] if action == 'defend' else []
            exchange['outcome'] = 'defended' if action == 'defend' else 'drew'
    elif action == 'rule8_drop' and played_cards:
        if not exchange or exchange.get('kind') != 'trail' or exchange.get('outcome') == 'crashed':
            exchange = {'id': payload['version'], 'kind': 'trail', 'attacker_index': actor_index,
                        'defender_index': 1 - actor_index if actor_index in (0, 1) else None,
                        'trail_cards': []}
        exchange = dict(exchange)
        exchange['trail_cards'] = (exchange.get('trail_cards', []) + list(played_cards))[-12:]
        exchange['outcome'] = 'trailing'
    elif action == 'rule8_crash' and exchange and exchange.get('kind') == 'trail':
        exchange = dict(exchange)
        exchange['outcome'] = 'crashed' if trail_crashed else 'continued'
    payload['exchange'] = exchange


def _exchange_event(payload, action, actor_index, fallback):
    exchange = payload.get('exchange')
    if not exchange or exchange.get('kind') != 'attack':
        return fallback
    name = payload['players'][actor_index]['name'] if actor_index in (0, 1) else 'Player'
    attack = exchange.get('attack_card')
    if action == 'attack':
        return f'{name} attacked with {attack}'
    if action == 'draw':
        return f'{name} could not defend {attack} and drew a hidden card'
    if action == 'defend' and exchange.get('defense_cards'):
        cards = exchange['defense_cards']
        values = [_card_value(card) for card in cards]
        equation = f" ({' + '.join(map(str, values))} = {exchange['target_value']})" if all(v is not None for v in values) else ''
        return f"{name} defended {attack} with {' + '.join(cards)}{equation}"
    return fallback


def _snapshot(room, manager, previous, state=None):
    match = public_match(room)
    if match is None:
        raise LookupError('This game is not available to spectators')
    tournament = db.session.get(Tournament, room.tournament_id)
    bracket = db.session.get(TournamentBracket, match.bracket_id) if match.bracket_id else None
    available = True
    if state is None:
        try:
            state = manager.get_game(room.game_id).get_state()
        except KeyError:
            state = None
            available = False
    players = []
    for index, user_id in enumerate((room.player1_id, room.player2_id)):
        user = db.session.get(User, user_id)
        count = None
        if state is not None:
            hands = state.get('hands', {})
            count = len(hands.get(index, hands.get(str(index), [])))
        elif previous.get('players') and index < len(previous['players']):
            count = previous['players'][index]['hand_count']
        players.append({'name': user.username if user else f'Player {index + 1}', 'hand_count': count})
    winner_index = None
    if room.winner_id in (room.player1_id, room.player2_id):
        winner_index = 0 if room.winner_id == room.player1_id else 1
    elif state is not None and state.get('winner') in (0, 1):
        winner_index = state['winner']
    completed = room.status == 'completed'
    exchange = previous.get('exchange')
    if state and state.get('attack_card') and (
        not exchange or exchange.get('attack_card') != state['attack_card']
        or exchange.get('outcome') not in {'pending', 'defended', 'drew'}
    ):
        exchange = _attack_exchange(state, f"active:{state['attack_card']}:{state.get('attacker')}")
    return {
        'room_code': room.room_code,
        'tournament_name': tournament.tournament_name,
        'is_promotional': bool(tournament.is_promotional),
        'round_name': bracket.round_name if bracket else 'Tournament match',
        'match_number': bracket.match_number if bracket else match.id,
        'bracket_url': f'/tournaments/{tournament.id}/bracket',
        'status': room.status,
        'available': available or completed,
        'players': players,
        'phase': state.get('phase') if state else None,
        'attacker': state.get('attacker') if state else None,
        'defender': state.get('defender') if state else None,
        'attack_card': state.get('attack_card') if state else None,
        'attack_card_value': state.get('attack_card_value') if state else None,
        'last_play': previous.get('last_play', []),
        'exchange': exchange,
        'winner_index': winner_index,
        'turn_deadline': _utc(room.turn_deadline) if room.status == 'in_progress' and available else None,
        'events': previous.get('events', [])[-12:],
        'version': max(time.time_ns() // 1000, previous.get('version', 0) + 1),
        'updated_at': _utc(datetime.utcnow()),
    }


def get_public_snapshot(room, manager):
    return _snapshot(room, manager, _read(room, manager))


def publish_spectator_update(socketio, room, state=None, action=None, actor_index=None, played_cards=None,
                             before_state=None, trail_crashed=None):
    """Best effort: spectators must never interrupt a committed player move."""
    try:
        if public_match(room) is None:
            return
        manager = current_app.extensions['game_manager']
        def build(previous):
            payload = _snapshot(room, manager, previous, state)
            if played_cards:
                payload['last_play'] = [str(card) for card in played_cards][:3]
            elif action == 'attack' and payload['attack_card']:
                payload['last_play'] = [payload['attack_card']]
            _update_exchange(payload, action, actor_index, played_cards, before_state, trail_crashed)
            labels = {
                'attack': 'played a card', 'defend': 'defended', 'draw': 'drew a card',
                'rule8_drop': 'played a trail card', 'rule8_crash': 'made a trail decision',
                'started': 'Match started', 'paused': 'Match paused',
                'resumed': 'Match resumed', 'completed': 'Match finished',
            }
            if action in labels:
                text = labels[action]
                if actor_index in (0, 1):
                    text = payload['players'][actor_index]['name'] + ' ' + text
                text = _exchange_event(payload, action, actor_index, text)
                payload['events'].append({'text': text, 'at': payload['updated_at']})
                payload['events'] = payload['events'][-12:]
            return payload
        payload = _save(room, manager, build)
        socketio.emit('spectator_update', payload, room=spectator_channel(room.room_code))
    except Exception:
        current_app.logger.exception('Spectator update failed room_id=%s', room.id)
