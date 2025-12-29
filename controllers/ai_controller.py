

import time
import random


class SimpleAIController:
    def __init__(self, engine, player_id, think_delay=0.9, jitter=0.6):
        self.engine = engine
        self.player_id = player_id
        # base delay in seconds before AI takes an action
        self.think_delay = think_delay
        # jitter to randomize thinking time
        self.jitter = jitter

    # -----------------------------
    # MAIN ENTRY
    # -----------------------------

    def play_if_needed(self):
        # Allow AI to perform multiple sequential actions that may change state
        # (e.g. defend successfully then immediately become attacker).
        # Protect against infinite loops with a max iteration count.
        max_iters = 6
        iters = 0
        while iters < max_iters:
            iters += 1
            state = self.engine.state
            if state.game_over:
                return

            acted = False

            if state.phase == "ATTACK" and state.attacker == self.player_id:
                print("[AI] It's my turn to attack:")
                self._think()
                self.handle_attack()
                acted = True

            if state.phase == "DEFENSE" and state.defender == self.player_id:
                self._think()
                defence_results = self.handle_defense()
                # Don't print defence_results as it may contain card objects with unicode
                acted = True

            if state.phase == "RULE_8" and state.attacker == self.player_id:
                self._think()
                self.handle_rule_8()
                acted = True

            # If no action was taken in this iteration, break out
            if not acted:
                break

    # -----------------------------
    # ATTACK
    # -----------------------------

    def handle_attack(self):
        player = self.engine.players[self.player_id]

        # Prefer highest valid attack
        candidates = [
            (i, c) for i, c in enumerate(player.hand)
            if 4 <= c.value <= 13
        ]

        if not candidates:
            print("[AI] No attack cards available")
            return

        index, card = max(candidates, key=lambda x: x[1].value)
        print(f"[AI] Attacks with card value {card.value}")

        self.engine.attack(self.player_id, index)

    # -----------------------------
    # DEFENSE
    # -----------------------------

    def handle_defense(self):
        defender = self.engine.players[self.player_id]
        attack_value = self.engine.state.attack_card.value

        # Try to find sum pair
        for i, c1 in enumerate(defender.hand):
            for j, c2 in enumerate(defender.hand):
                if i != j and c1.value + c2.value == attack_value:
                    print(f"[AI] Defends with {c1.value} + {c2.value} = {attack_value}")
                    defend_results = self.engine.defend(self.player_id, i, j)
                    return defend_results

        # No defense → draw
        print("[AI] Cannot defend, drawing")
        self.engine.defender_draw(self.player_id)

    # -----------------------------
    # RULE 8
    # -----------------------------

    def handle_rule_8(self):
        player = self.engine.players[self.player_id]

        # Drop highest low card first
        for value in (3, 2, 1):
            if any(c.value == value for c in player.hand):
                print(f"[AI] Rule 8 drops {value}")
                self.engine.rule_8_drop(self.player_id, value)
                return

    def _think(self):
        """Sleep a short randomized interval to simulate AI thinking."""
        delay = self.think_delay + random.random() * self.jitter
        time.sleep(delay)
