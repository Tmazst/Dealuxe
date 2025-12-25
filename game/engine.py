from game.models import Deck, GameState
from game.rules import is_winner, has_attack_card, is_low_only


class CardGameEngine:
    def __init__(self, players):
        self.deck = Deck()
        self.players = players
        self.state = GameState()

        # Deal cards
        for _ in range(6):
            for p in self.players:
                p.draw_card(self.deck)

        print("[ENGINE] Game initialized")

    # ---------------------
    # STATE HELPERS-
    # ---------------------

    def get_state(self):
        """
        Returns a serializable snapshot of the game.
        """
        return {
            "phase": self.state.phase,
            "attacker": self.state.attacker,
            "defender": self.state.defender,
            "attack_card": str(self.state.attack_card) if self.state.attack_card else None,
            "attack_card_value": self.state.attack_card.value if self.state.attack_card else None,
            "hands": {
                i: [str(c) for c in p.hand]
                for i, p in enumerate(self.players)
            }
        }

    def _check_winner(self):
        for i, p in enumerate(self.players):
            if is_winner(p):
                self.state.game_over = True
                self.state.winner = i
                self.state.phase = "GAME_OVER"
                print(f"[ENGINE] Player {i} wins")

    # ---------------------
    # TURN CONTROL
    # ---------------------

    def start_turn(self):
        print(f"[ENGINE] Player {self.state.attacker}'s turn begins")

        attacker = self.players[self.state.attacker]

        # Rule 8 auto-entry
        if not has_attack_card(attacker) and is_low_only(attacker) and len(attacker.hand) > 3:
            self.state.phase = "RULE_8"
            print("[ENGINE] Rule 8 triggered automatically")

        self._check_winner()

    # ---------------------
    # ATTACK PHASE
    # ---------------------

    def attack(self, player_id, card_index):
        # print(f'[ENGINE] ATTACK Phase: {self.state.phase}, ID {player_id}')
        assert self.state.phase == "ATTACK"

        attacker = self.players[player_id]
        # Validate index to avoid IndexError when callers pass stale indices
        if card_index < 0 or card_index >= len(attacker.hand):
            return {"error": "Invalid index"}

        card = attacker.hand[card_index]

        if not (4 <= card.value <= 13):
            return {"error": "Invalid attack card"}

        attacker.hand.remove(card)
        self.state.attack_card = card
        self.state.phase = "DEFENSE"

        print(f"[ENGINE] Player {player_id} attacks with {card}")

        return {"ok": True}

    # ---------------------
    # DEFENSE PHASE
    # ---------------------

    def defend(self, player_id, i1, i2):
        assert self.state.phase == "DEFENSE"

        defender = self.players[player_id]
        c1 = defender.hand[i1]
        c2 = defender.hand[i2]

        if c1.value + c2.value != self.state.attack_card.value:
            return {"error": "Invalid sum"}

        defender.hand.remove(c1)
        defender.hand.remove(c2)

        print(f"[ENGINE] Defense successful: {c1} + {c2}")

        self._check_winner()

        # swap turns
        self.state.attacker, self.state.defender = (
            self.state.defender,
            self.state.attacker,
        )
        self.state.attack_card = None
        self.state.phase = "ATTACK"
        self.state.defence_cards = [str(c1),str(c2)]

        return {"ok": True, "success": True,"used_cards": [str(c1), str(c2)],
                "phase": self.state.phase, "attacker": self.state.attacker, "used_indices": [i1, i2]}


    def defender_draw(self, player_id):
        defender = self.players[player_id]
        card = defender.draw_card(self.deck)

        print(f"[ENGINE] Defender failed to defend and draws {card}")

        # Defense failed → attacker keeps the turn
        self.state.attack_card = None
        self.state.phase = "ATTACK"

        self.state.defender_drawn_card = str(card) if card else None

        print("[ENGINE] Defense failed. Attacker gets another turn.")

        return {
            "drawn": str(card) if card else None,
            "next_phase": self.state.phase,
            "attacker": self.state.attacker
        }


    # ---------------------
    # RULE 8 PHASE
    # ---------------------

    def rule_8_drop(self, player_id, value):
        assert self.state.phase == "RULE_8"

        attacker = self.players[player_id]

        cards = [c for c in attacker.hand if c.value == value]
        if not cards:
            return {"error": "No such card to drop"}

        dropped = cards[0]
        attacker.hand.remove(dropped)

        print(f"[ENGINE] Rule 8 drop: {dropped}")

        self.state.trail_value = value
        self._check_winner()

        return {"dropped": str(dropped)}

    def rule_8_crash(self, defender_id, crash):
        assert self.state.phase == "RULE_8"

        defender = self.players[defender_id]

        if crash and any(c.value == self.state.trail_value for c in defender.hand):
            print("[ENGINE] Trail crashed")
            self.players[self.state.attacker].draw_card(self.deck)

            self.state.phase = "ATTACK"
            self.state.trail_value = None
            return {"crashed": True}

        print("[ENGINE] Trail continues")
        return {"crashed": False}

    def consume_ui_state(self):
        data = {
            "defence_cards": self.state.defence_cards,
            "defender_drawn_card": self.state.defender_drawn_card,
            "attack_card": str(self.state.attack_card) if self.state.attack_card else None,
            "phase": self.state.phase,
            "attacker": self.state.attacker,
            "defender": self.state.defender,
            "game_over": self.state.game_over,
            "winner": self.state.winner,
            "hands": {
                i: [str(c) for c in p.hand]
                for i, p in enumerate(self.players)
            }
        }

        # clear transient fields
        self.state.defence_cards = None
        self.state.defender_drawn_card = None
        # print("consume_ui_state: ",data)
        return data