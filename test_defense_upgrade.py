import pytest

from game.engine import CardGameEngine
from game.models import Card, Player


def build_engine_for_defense():
    players = [Player("Player 1"), Player("Player 2")]
    engine = CardGameEngine(players, cards_per_player=0)

    engine.players[0].hand = [
        Card("2", "♥", 2),
        Card("3", "♦", 3),
        Card("4", "♣", 4),
        Card("5", "♠", 5),
    ]
    engine.players[1].hand = [
        Card("A", "♥", 1),
        Card("4", "♣", 4),
        Card("5", "♠", 5),
    ]

    engine.state.phase = "DEFENSE"
    engine.state.attacker = 0
    engine.state.defender = 1
    engine.state.attack_card = Card("10", "♠", 10)
    return engine


def test_defend_accepts_three_cards_when_sum_matches_attack_value():
    engine = build_engine_for_defense()

    result = engine.defend(1, [0, 1, 2])

    assert result["ok"] is True
    assert result["success"] is True
    assert engine.players[1].hand == []
    assert engine.state.phase == "GAME_OVER"
    assert result["winner"] == 1


def test_defend_rejects_duplicate_indices_and_invalid_lengths():
    engine = build_engine_for_defense()

    duplicate_result = engine.defend(1, [0, 0])
    assert duplicate_result["error"] == "Cannot use the same card twice"

    invalid_length_result = engine.defend(1, [0, 1, 2, 3])
    assert invalid_length_result["error"] == "Defense requires 2 or 3 cards, got 4"
