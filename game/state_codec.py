"""Strict, versioned JSON codec for Redis-backed game sessions.

The decoder reconstructs only the small set of Dealuxe model types listed
here. Redis contents cannot select Python callables or arbitrary classes.
"""

import json
import math

from game.engine import CardGameEngine
from game.models import Card, Deck, GameState, Player


SCHEMA_NAME = 'umshova.game-session'
SCHEMA_VERSION = 1
DEFAULT_MAX_PAYLOAD_BYTES = 256 * 1024

_RANK_VALUES = {
    'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13,
}
_SUITS = {'♥', '♦', '♣', '♠'}
_PHASES = {'ATTACK', 'DEFENSE', 'RULE_8', 'GAME_OVER'}
_MODES = {'human_vs_ai', 'local'}
_STATUSES = {'active', 'completed', 'cancelled'}


class GameStateCodecError(ValueError):
    """Stable validation error whose code is safe to log."""

    def __init__(self, code):
        self.code = str(code)
        super().__init__(self.code)


def _object(value, fields, code='invalid_schema'):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise GameStateCodecError(code)
    return value


def _integer(value, minimum, maximum, code='invalid_schema'):
    if isinstance(value, bool) or not isinstance(value, int):
        raise GameStateCodecError(code)
    if value < minimum or value > maximum:
        raise GameStateCodecError(code)
    return value


def _number(value, minimum=0, code='invalid_schema'):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GameStateCodecError(code)
    if not math.isfinite(value) or value < minimum:
        raise GameStateCodecError(code)
    return float(value)


def _text(value, maximum, code='invalid_schema', allow_empty=True):
    if not isinstance(value, str) or len(value) > maximum:
        raise GameStateCodecError(code)
    if not allow_empty and not value:
        raise GameStateCodecError(code)
    return value


def _optional_text(value, maximum):
    if value is None:
        return None
    return _text(value, maximum)


def _card_to_data(card):
    if not isinstance(card, Card):
        raise GameStateCodecError('invalid_card')
    data = {'rank': card.rank, 'suit': card.suit, 'value': card.value}
    _validate_card(data)
    return data


def _validate_card(data):
    _object(data, {'rank', 'suit', 'value'}, 'invalid_card')
    rank = _text(data['rank'], 2, 'invalid_card', allow_empty=False)
    suit = _text(data['suit'], 1, 'invalid_card', allow_empty=False)
    value = _integer(data['value'], 1, 13, 'invalid_card')
    if suit not in _SUITS or _RANK_VALUES.get(rank) != value:
        raise GameStateCodecError('invalid_card')
    return data


def _card_from_data(data):
    _validate_card(data)
    return Card(data['rank'], data['suit'], data['value'])


def _state_to_data(state):
    if not isinstance(state, GameState):
        raise GameStateCodecError('invalid_state')
    defence_cards = state.defence_cards
    if defence_cards is not None:
        if not isinstance(defence_cards, list) or len(defence_cards) > 3:
            raise GameStateCodecError('invalid_state')
        defence_cards = [_text(value, 3) for value in defence_cards]
    return {
        'phase': state.phase,
        'attacker': state.attacker,
        'defender': state.defender,
        'mode': state.mode,
        'attack_card': _card_to_data(state.attack_card) if state.attack_card else None,
        'trail_value': state.trail_value,
        'game_over': state.game_over,
        'winner': state.winner,
        'defence_cards': defence_cards,
        'defender_drawn_card': state.defender_drawn_card,
    }


def _validate_state(data):
    fields = {
        'phase', 'attacker', 'defender', 'mode', 'attack_card', 'trail_value',
        'game_over', 'winner', 'defence_cards', 'defender_drawn_card',
    }
    _object(data, fields, 'invalid_state')
    if data['phase'] not in _PHASES or data['mode'] not in _MODES:
        raise GameStateCodecError('invalid_state')
    attacker = _integer(data['attacker'], 0, 1, 'invalid_state')
    defender = _integer(data['defender'], 0, 1, 'invalid_state')
    if attacker == defender or not isinstance(data['game_over'], bool):
        raise GameStateCodecError('invalid_state')
    if data['winner'] is not None:
        _integer(data['winner'], 0, 1, 'invalid_state')
    if data['trail_value'] is not None:
        _integer(data['trail_value'], 1, 13, 'invalid_state')
    if data['attack_card'] is not None:
        _validate_card(data['attack_card'])
    defence_cards = data['defence_cards']
    if defence_cards is not None:
        if not isinstance(defence_cards, list) or len(defence_cards) > 3:
            raise GameStateCodecError('invalid_state')
        for value in defence_cards:
            _text(value, 3, 'invalid_state')
    _optional_text(data['defender_drawn_card'], 3)
    if data['game_over'] != (data['phase'] == 'GAME_OVER'):
        raise GameStateCodecError('invalid_state')
    if data['game_over'] != (data['winner'] is not None):
        raise GameStateCodecError('invalid_state')
    return data


def _state_from_data(data):
    _validate_state(data)
    state = GameState()
    state.phase = data['phase']
    state.attacker = data['attacker']
    state.defender = data['defender']
    state.mode = data['mode']
    state.attack_card = _card_from_data(data['attack_card']) if data['attack_card'] else None
    state.trail_value = data['trail_value']
    state.game_over = data['game_over']
    state.winner = data['winner']
    state.defence_cards = list(data['defence_cards']) if data['defence_cards'] is not None else None
    state.defender_drawn_card = data['defender_drawn_card']
    return state


def _engine_to_data(engine):
    if not isinstance(engine, CardGameEngine) or len(engine.players) != 2:
        raise GameStateCodecError('invalid_engine')
    players = []
    for player in engine.players:
        if not isinstance(player, Player) or len(player.hand) > 52:
            raise GameStateCodecError('invalid_player')
        players.append({
            'name': _text(player.name, 80, 'invalid_player', allow_empty=False),
            'hand': [_card_to_data(card) for card in player.hand],
        })
    if not isinstance(engine.deck, Deck) or len(engine.deck.cards) > 52:
        raise GameStateCodecError('invalid_deck')
    if not isinstance(engine.ui_log, list) or len(engine.ui_log) > 500:
        raise GameStateCodecError('invalid_ui_log')
    return {
        'players': players,
        'deck': [_card_to_data(card) for card in engine.deck.cards],
        'state': _state_to_data(engine.state),
        'ui_log': [_text(item, 500, 'invalid_ui_log') for item in engine.ui_log],
    }


def _validate_engine(data):
    _object(data, {'players', 'deck', 'state', 'ui_log'}, 'invalid_engine')
    if not isinstance(data['players'], list) or len(data['players']) != 2:
        raise GameStateCodecError('invalid_player')
    active_cards = []
    for player in data['players']:
        _object(player, {'name', 'hand'}, 'invalid_player')
        _text(player['name'], 80, 'invalid_player', allow_empty=False)
        if not isinstance(player['hand'], list) or len(player['hand']) > 52:
            raise GameStateCodecError('invalid_player')
        for card in player['hand']:
            _validate_card(card)
            active_cards.append(card)
    if not isinstance(data['deck'], list) or len(data['deck']) > 52:
        raise GameStateCodecError('invalid_deck')
    for card in data['deck']:
        _validate_card(card)
        active_cards.append(card)
    _validate_state(data['state'])
    if data['state']['attack_card'] is not None:
        active_cards.append(data['state']['attack_card'])
    identities = [(card['rank'], card['suit']) for card in active_cards]
    if len(identities) != len(set(identities)):
        raise GameStateCodecError('duplicate_active_card')
    if not isinstance(data['ui_log'], list) or len(data['ui_log']) > 500:
        raise GameStateCodecError('invalid_ui_log')
    for item in data['ui_log']:
        _text(item, 500, 'invalid_ui_log')
    return data


def _engine_from_data(data):
    _validate_engine(data)
    players = []
    for player_data in data['players']:
        player = Player(player_data['name'])
        player.hand = [_card_from_data(card) for card in player_data['hand']]
        players.append(player)
    deck = Deck.__new__(Deck)
    deck.cards = [_card_from_data(card) for card in data['deck']]
    engine = CardGameEngine.__new__(CardGameEngine)
    engine.deck = deck
    engine.players = players
    engine.state = _state_from_data(data['state'])
    engine.ui_log = list(data['ui_log'])
    return engine


def session_to_document(session_data):
    """Convert the current in-memory session to schema-version-one data."""
    _object(session_data, {'engine', 'mode', 'created_at', 'status', 'players', 'card_count'}, 'invalid_session')
    engine = session_data['engine']
    if session_data['players'] is not engine.players:
        raise GameStateCodecError('invalid_session')
    mode = session_data['mode']
    status = session_data['status']
    if mode not in _MODES or status not in _STATUSES:
        raise GameStateCodecError('invalid_session')
    card_count = _integer(session_data['card_count'], 1, 52, 'invalid_session')
    if card_count not in {6, 8, 10}:
        raise GameStateCodecError('invalid_session')
    document = {
        'schema': SCHEMA_NAME,
        'version': SCHEMA_VERSION,
        'session': {
            'mode': mode,
            'created_at': _number(session_data['created_at'], code='invalid_session'),
            'status': status,
            'card_count': card_count,
            'engine': _engine_to_data(engine),
        },
    }
    _validate_document(document)
    return document


def _validate_document(document):
    _object(document, {'schema', 'version', 'session'})
    if document['schema'] != SCHEMA_NAME:
        raise GameStateCodecError('unknown_schema')
    if document['version'] != SCHEMA_VERSION:
        raise GameStateCodecError('unsupported_version')
    session = _object(document['session'], {'mode', 'created_at', 'status', 'card_count', 'engine'}, 'invalid_session')
    if session['mode'] not in _MODES or session['status'] not in _STATUSES:
        raise GameStateCodecError('invalid_session')
    _number(session['created_at'], code='invalid_session')
    if _integer(session['card_count'], 1, 52, 'invalid_session') not in {6, 8, 10}:
        raise GameStateCodecError('invalid_session')
    _validate_engine(session['engine'])
    return document


def encode_session(session_data, max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES):
    """Return deterministic UTF-8 JSON bytes after complete schema validation."""
    payload = json.dumps(
        session_to_document(session_data), ensure_ascii=False, allow_nan=False,
        separators=(',', ':'), sort_keys=True,
    ).encode('utf-8')
    if len(payload) > int(max_payload_bytes):
        raise GameStateCodecError('payload_too_large')
    return payload


def _reject_constant(_value):
    raise GameStateCodecError('invalid_json_number')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GameStateCodecError('duplicate_json_key')
        result[key] = value
    return result


def decode_session(payload, max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES):
    """Decode only the current safe schema; legacy/object payloads are rejected."""
    if not isinstance(payload, (bytes, bytearray, str)):
        raise GameStateCodecError('invalid_payload_type')
    raw = payload.encode('utf-8') if isinstance(payload, str) else bytes(payload)
    if not raw or len(raw) > int(max_payload_bytes):
        raise GameStateCodecError('payload_too_large' if raw else 'empty_payload')
    try:
        document = json.loads(
            raw.decode('utf-8'), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except GameStateCodecError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        raise GameStateCodecError('invalid_json')
    _validate_document(document)
    session = document['session']
    engine = _engine_from_data(session['engine'])
    return {
        'engine': engine,
        'mode': session['mode'],
        'created_at': float(session['created_at']),
        'status': session['status'],
        'players': engine.players,
        'card_count': session['card_count'],
    }
