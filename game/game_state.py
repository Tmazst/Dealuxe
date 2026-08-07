"""
*** NOT USED BY THE RUNNING APP -- KEPT FOR REFERENCE ONLY ***

This is a second, unrelated GameState/Deck pair (dict-based cards, 5-card
default deal) that is not imported anywhere in the codebase. The real
GameState/Deck the engine actually runs on live in game/models.py and
game/deck.py, and are used throughout game/engine.py.

Confirmed via `grep -rn "game_state import" .` and `grep -rn "game.game_state" .`
across the whole repo (2026-07-27 audit) -- zero importers.

Left in place rather than deleted per project decision -- if this is ever
wired back in, note it uses plain dicts for cards ({"suit":..., "rank":...})
with no `value` field, which is NOT compatible with game/rules.py's
is_winner()/has_attack_card() (they expect Card objects with `.value`).
Mixing this into the live engine as-is would break win-condition checks.
"""

from game.deck import Deck

class GameState:
    def __init__(self):
        self.deck = Deck()
        self.deck.shuffle()
        self.players = {}
        self.turn = None

    def add_player(self, player_id):
        self.players[player_id] = {
            "hand": [],
            "score": 0
        }

    def deal(self, cards_per_player=5):
        for player in self.players:
            self.players[player]["hand"] = self.deck.draw(cards_per_player)

    def play_card(self, player_id, card_index):
        card = self.players[player_id]["hand"].pop(card_index)
        return card

