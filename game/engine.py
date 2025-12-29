from game.models import Deck, GameState
from game.rules import is_winner, has_attack_card, is_low_only

# Helper to safely print messages with potential unicode characters
def safe_print(msg):
    """Print message safely, handling unicode encoding errors"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback: replace unicode chars with ? for ASCII-only environments
        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
        print(safe_msg)

'''
[**UPDATE 27 December 2025**]
[**THE 4 CONDITIONS OF WINNING THE DEALUXE GAME**]
Note: The DEALUXE WIN, ECSAPE WIN, TRAIL WIN conditions are are under the normal and main; HAND <= 3 rule

1. DEALUXE WIN:
An attacker should always win after a failed defense from the opponent.
e.g. If an attacker's hand has [2,3,8]. When they attack with the [8] they dont automatically
win, the defender has to fail and draw a card first then the attacker wins. The drawing of the
card tells us that the defender did not have defending cards before they draw or they mistakely
draw when they were not supposed to. Drawing of the cards triggers a win for attacker. its a DEALUXE WIN.

2. ESCAPE WIN:
A win for defender should take place immediately when the successfully defended their position.
e.g. attacker played [J], defender's hand[3,8,A]. If defender defends succefully with [3,8] that 
automatically triggers a win (without any drawing of card). its an ESCAPE WIN.

3. CRAZY ESCAPE WIN:
If defender draws a card (failed to defend) while attacker has count=0 (Left with no card after an attack).
It means the attacker was left with an attacking card(4-13) e.g. a [Q],before the latest attack.
But if the defender defended well e.g. with [7,5] the game would proceed normally.

4. TRAIL WIN (RULE #8 WIN):
When the attacker is left with winning cards i.e. any of [A,2,3] but they are more 3 lets with 5 cards [A,2,2,3,A].
The attacker must drop each card until they reach 3. But during trail they attacker should pray that 
defender must not have any of the cards they at a time, if the defender have the card dropped in their HAND, 
they are allowed to crash the trail. The will proceed normally after a successful crash.

Note: DEALUXE WIN, CRAZY ESCAPE WIN, TRAIL WIN are triggered by defender_draw method and ESCAPE WIN is triggered by defence method.
'''


class CardGameEngine:
    def __init__(self, players):
        self.deck = Deck()
        self.players = players
        self.state = GameState()
        self.ui_log = []

        # Deal cards
        for _ in range(6):
            for p in self.players:
                p.draw_card(self.deck)

        safe_print("[ENGINE] Game initialized")

    # ---------------------
    # STATE HELPERS-
    # ---------------------
    def get_state(self):
        return {
            "phase": self.state.phase,
            "attacker": self.state.attacker,
            "defender": self.state.defender,
            "attack_card": str(self.state.attack_card) if self.state.attack_card else None,
            "attack_card_value": self.state.attack_card.value if self.state.attack_card else None,
            "hands": {i: [str(c) for c in p.hand] for i, p in enumerate(self.players)},
            "game_over": self.state.game_over,
            "winner": self.state.winner,
            "ui_log": list(self.ui_log),
        }


    def _log(self, msg):
        # print to console and append to ui log for frontend consumption
        # Use safe printing to avoid unicode encoding errors on VPS
        try:
            print(msg)
        except UnicodeEncodeError:
            # Fallback: print ASCII-safe version
            safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
            print(safe_msg)
        self.ui_log.append(msg)

    def _check_winner(self):
        for i, p in enumerate(self.players):
            if is_winner(p):
                self.state.game_over = True
                self.state.winner = i
                self.state.phase = "GAME_OVER"
                safe_print(f"[ENGINE] Player {i} wins")

    # ---------------------
    # TURN CONTROL
    # ---------------------

    def start_turn(self):
        self._log(f"[ENGINE] Player {self.state.attacker}'s turn begins")

        attacker = self.players[self.state.attacker]

        # Rule 8 auto-entry
        if not has_attack_card(attacker) and is_low_only(attacker) and len(attacker.hand) > 3:
            self.state.phase = "RULE_8"
            safe_print("[ENGINE] Rule 8 triggered automatically")

        # self._check_winner()

    # ---------------------
    # ATTACK PHASE
    # ---------------------

    def attack(self, player_id, card_index):
        safe_print(f"[ENGINE] attack called - player_id: {player_id}, card_index: {card_index}, phase: {self.state.phase}")
        
        if self.state.game_over:
            safe_print("[ENGINE] GAME WAS OVER - attack")
            return {"error": "Game is already over"}
        
        # Better error handling instead of assert
        if self.state.phase != "ATTACK":
            error_msg = f"Cannot attack during {self.state.phase} phase. Expected ATTACK phase."
            safe_print(f"[ENGINE] {error_msg}")
            return {"error": error_msg, "current_phase": self.state.phase}

        attacker = self.players[player_id]
        safe_print(f"[ENGINE] Attacker has {len(attacker.hand)} cards: {[c.value for c in attacker.hand]}")
        
        # Validate index to avoid IndexError when callers pass stale indices
        if card_index < 0 or card_index >= len(attacker.hand):
            safe_print(f"[ENGINE] Invalid card index: {card_index}")
            return {"error": "Invalid index"}

        card = attacker.hand[card_index]

        if not (4 <= card.value <= 13):
            safe_print(f"[ENGINE] Invalid attack card value: {card.value}")
            return {"error": "Invalid attack card"}

        attacker.hand.remove(card)
        self.state.attack_card = card
        self.state.phase = "DEFENSE"
        safe_print(f"[ENGINE] Phase transition: ATTACK -> DEFENSE")
        safe_print(f"[ENGINE] Attacker now has {len(attacker.hand)} cards left")

        self._log(f"[ENGINE] Player {player_id} attacks with card value {card.value}")

        return {"ok": True}

    # ---------------------
    # DEFENSE PHASE
    # ---------------------

    def defend(self, player_id, i1, i2):
        if self.state.game_over:
            safe_print("[ENGINE] GAME WAS OVER - defend")
            return {"error": "Game is already over"}
        
        # Better error handling instead of assert
        if self.state.phase != "DEFENSE":
            error_msg = f"Cannot defend during {self.state.phase} phase. Expected DEFENSE phase."
            safe_print(f"[ENGINE] {error_msg}")
            return {"error": error_msg, "current_phase": self.state.phase}
        
        DEFENCE_SUCCESSFUL = True

        defender = self.players[player_id]
        c1 = defender.hand[i1]
        c2 = defender.hand[i2]

        if c1.value + c2.value != self.state.attack_card.value:
            DEFENCE_SUCCESSFUL = False
            return {"error": "Invalid sum"}

        defender.hand.remove(c1)
        defender.hand.remove(c2)

        self._log(f"[ENGINE] Defense successful: {c1.value} + {c2.value} = {self.state.attack_card.value}")

        # Check for ESCAPE WIN - Defender wins immediately after successful defense
        defender = self.players[player_id]
        if is_winner(defender):
            '''ESCAPE WIN'''
            self.state.game_over = True
            self.state.winner = player_id
            self.state.phase = "GAME_OVER"
            safe_print(f"[ENGINE] Player {player_id} wins by ESCAPE WIN")
            self._log(f"[ENGINE] Player {player_id} wins by ESCAPE WIN")
            # Return immediately - don't swap turns or change phase
            self.state.defence_cards = [str(c1), str(c2)]
            return {"ok": True, "success": True, "used_cards": [str(c1), str(c2)],
                    "phase": self.state.phase, "attacker": self.state.attacker, "used_indices": [i1, i2],
                    "game_over": True, "winner": player_id}

        # swap turns
        self.state.attacker, self.state.defender = (
            self.state.defender,
            self.state.attacker,
        )
        self.state.attack_card = None
        self.state.phase = "ATTACK"
        safe_print(f"[ENGINE] Phase transition: DEFENSE -> ATTACK (roles swapped, new attacker: {self.state.attacker})")
        self.state.defence_cards = [str(c1),str(c2)]

        return {"ok": True, "success": True,"used_cards": [str(c1), str(c2)],
                "phase": self.state.phase, "attacker": self.state.attacker, "used_indices": [i1, i2]}


    def defender_draw(self, player_id):
        safe_print(f"[ENGINE] defender_draw called - player_id: {player_id}, phase: {self.state.phase}, game_over: {self.state.game_over}")
        
        if self.state.game_over:
            safe_print("[ENGINE] GAME WAS OVER - draw")
            return {"error": "Game is already over"}
         
        defender = self.players[player_id]
        safe_print(f"[ENGINE] Defender {player_id} has {len(defender.hand)} cards before draw")
        
        card = defender.draw_card(self.deck)
        safe_print(f"[ENGINE] Defender drew card, now has {len(defender.hand)} cards")

        # Check win conditions after defender draws (failed defense)
        attacker = self.players[self.state.attacker]
        safe_print(f"[ENGINE] Attacker {self.state.attacker} has {len(attacker.hand)} cards: {[c.value for c in attacker.hand]}")

        # Check if attacker Win after this card draw? 
        if len(attacker.hand) == 0 and self.state.attack_card and 4 <= self.state.attack_card.value <= 13: 
            '''
            CRAZY ESCAPE WIN 
            '''
            safe_print(f"[ENGINE] CRAZY ESCAPE WIN triggered - attacker has 0 cards")
            self.state.game_over = True
            self.state.winner = self.state.attacker
            self.state.phase = "GAME_OVER"
            safe_print(f"[ENGINE] Player {self.state.attacker} wins by ZERO COUNT - CRAZY ESCAPE WIN")
            self._log(f"[ENGINE] Player {self.state.attacker} wins by CRAZY ESCAPE WIN")
            return {
                "drawn": str(card) if card else None,
                "next_phase": self.state.phase,
                "attacker": self.state.attacker,
                "game_over": True,
                "winner": self.state.attacker
            }
        
        # Check for DEALUXE WIN - Attacker wins when defender fails to defend
        safe_print(f"[ENGINE] Checking DEALUXE WIN - is_winner(attacker): {is_winner(attacker)}")
        if is_winner(attacker):
            '''
            DEALUXE WIN
            '''
            safe_print(f"[ENGINE] DEALUXE WIN triggered")
            self.state.game_over = True
            self.state.winner = self.state.attacker
            self.state.phase = "GAME_OVER"
            safe_print(f"[ENGINE] Player {self.state.attacker} wins by DEALUXE WIN")
            self._log(f"[ENGINE] Player {self.state.attacker} wins by DEALUXE WIN")
            return {
                "drawn": str(card) if card else None,
                "next_phase": self.state.phase,
                "attacker": self.state.attacker,
                "game_over": True,
                "winner": self.state.attacker
            }

        # Do not reveal drawn card identities in UI log
        self._log(f"[ENGINE] Defender failed to defend and draws a card")

        # Defense failed -> attacker keeps the turn
        self.state.attack_card = None
        self.state.phase = "ATTACK"
        safe_print(f"[ENGINE] Phase transition: DEFENSE -> ATTACK (defense failed, attacker {self.state.attacker} keeps turn)")

        self.state.defender_drawn_card = str(card) if card else None

        self._log("[ENGINE] Defense failed. Attacker gets another turn.")
        
        safe_print(f"[ENGINE] defender_draw completed successfully - returning to phase: {self.state.phase}")

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

        self._log(f"[ENGINE] Rule 8 drop: value {dropped.value}")

        self.state.trail_value = value

        return {"dropped": str(dropped)}

    def rule_8_crash(self, defender_id, crash):
        assert self.state.phase == "RULE_8"

        defender = self.players[defender_id]
        attacker = self.players[self.state.attacker]

        if crash and any(c.value == self.state.trail_value for c in defender.hand):
            self._log("[ENGINE] Trail crashed")
            attacker.draw_card(self.deck)

            self.state.phase = "ATTACK"
            self.state.trail_value = None
            return {"crashed": True}

        # Defender didn't crash - check for TRAIL WIN
        if is_winner(attacker):
            '''
            TRAIL WIN - Attacker reached ≤3 low cards and defender failed to crash
            '''
            self.state.game_over = True
            self.state.winner = self.state.attacker
            self.state.phase = "GAME_OVER"
            safe_print(f"[ENGINE] Player {self.state.attacker} wins by TRAIL WIN")
            self._log(f"[ENGINE] Player {self.state.attacker} wins by TRAIL WIN")
            return {"crashed": False, "game_over": True, "winner": self.state.attacker}

        self._log("[ENGINE] Trail continues")
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

        # include ui log and then clear transient fields
        data["ui_log"] = list(self.ui_log)
        self.ui_log.clear()

        # clear transient fields
        self.state.defence_cards = None
        self.state.defender_drawn_card = None
        return data