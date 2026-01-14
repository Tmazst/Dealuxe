from flask import jsonify
from controllers.ai_controller import SimpleAIController

class FlaskGameController:
    def __init__(self, engine):
        self.engine = engine
        # By default run AI (used for human_vs_ai mode). Callers can disable AI by
        # passing run_ai=False when constructing this controller (e.g. multiplayer).
        self._run_ai_enabled = True
        self.ai = SimpleAIController(engine, player_id=1)

    def __init__(self, engine, run_ai=True, ai_player_id=1):
        self.engine = engine
        self._run_ai_enabled = bool(run_ai)
        self.ai = SimpleAIController(engine, player_id=ai_player_id) if self._run_ai_enabled else None

    def get_state(self):
        return jsonify(self.engine.get_state())

    def start_turn(self):
        self.engine.start_turn()
        return jsonify(self.engine.get_state())

    def attack(self, card_index):
        attacker = self.engine.state.attacker
        print(f"[FLASK_CTRL] Attack request - Phase: {self.engine.state.phase}, Attacker: {attacker}, Card: {card_index}")
        
        result = self.engine.attack(attacker, card_index)
        
        # Only run AI if attack was successful and AI is enabled for this controller
        defend_results = None
        if result.get('ok'):
            if self._run_ai_enabled:
                defend_results = self._run_ai_if_needed()
        else:
            print(f"[FLASK_CTRL] Attack failed: {result.get('error')}")
        
        # Return transient UI state (and consume it) so frontend receives
        # defence/defender_drawn info produced by the AI in the same request.
        return jsonify({'defence_results': defend_results, 'results': result, 'ui_state': self.engine.consume_ui_state()})

    def defend(self, idx1, idx2):
        defender = self.engine.state.defender
        print(f"[FLASK_CTRL] Defend request - Phase: {self.engine.state.phase}, Defender: {defender}")
        
        result = self.engine.defend(defender, idx1, idx2)
        
        # Only run AI if defend was successful and AI is enabled
        if not result.get('error') and self._run_ai_enabled:
            self._run_ai_if_needed()
        else:
            print(f"[FLASK_CTRL] Defend failed: {result.get('error')}")
        
        return jsonify({**result, **self.engine.consume_ui_state()})

    def draw(self):
        defender = self.engine.state.defender
        print(f"[FLASK_CTRL] Draw request - Phase: {self.engine.state.phase}, Defender: {defender}")
        
        result = self.engine.defender_draw(defender)
        
        # Handle None result (shouldn't happen anymore, but safety check)
        if result is None:
            print("[FLASK_CTRL] ERROR: defender_draw returned None!")
            result = {"error": "Draw failed - no result returned"}
        
        # Only run AI if draw was successful and AI is enabled
        if not result.get('error') and self._run_ai_enabled:
            print("[FLASK_CTRL] Running AI after defender draw")
            self._run_ai_if_needed()
        else:
            print(f"[FLASK_CTRL] Draw had error: {result.get('error')}")
        
        return jsonify({**result, **self.engine.consume_ui_state()})

    def rule_8_drop(self, value):
        attacker = self.engine.state.attacker
        result = self.engine.rule_8_drop(attacker, value)
        return jsonify({**result, **self.engine.consume_ui_state()})

    def rule_8_crash(self, crash):
        defender = self.engine.state.defender
        result = self.engine.rule_8_crash(defender, crash)
        if self._run_ai_enabled:
            self._run_ai_if_needed()
        return jsonify({**result, **self.engine.consume_ui_state()})
    
    def _run_ai_if_needed(self):
        if self.ai:
            return self.ai.play_if_needed()
        return None

    def leaderboard(self):
        # Build a simple leaderboard from current players preserving existing data
        players = []
        for i, p in enumerate(self.engine.players):
            players.append({
                "id": i,
                "name": p.name,
                "hand_count": len(p.hand),
                "hand": [str(c) for c in p.hand]
            })

        data = {
            "players": players,
            "phase": self.engine.state.phase,
            "attacker": self.engine.state.attacker,
            "defender": self.engine.state.defender
        }

        return jsonify(data)
