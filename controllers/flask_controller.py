from flask import jsonify
from controllers.ai_controller import SimpleAIController

class FlaskGameController:
    def __init__(self, engine):
        self.engine = engine
        self.ai = SimpleAIController(engine, player_id=1)

    def get_state(self):
        return jsonify(self.engine.get_state())

    def start_turn(self):
        self.engine.start_turn()
        return jsonify(self.engine.get_state())

    def attack(self, card_index):
        attacker = self.engine.state.attacker
        print(f"[FLASK_CTRL] Attack request - Phase: {self.engine.state.phase}, Attacker: {attacker}, Card: {card_index}")
        
        result = self.engine.attack(attacker, card_index)
        
        # Only run AI if attack was successful
        defend_results = None
        if result.get('ok'):
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
        
        # Only run AI if defend was successful
        if not result.get('error'):
            self._run_ai_if_needed()
        else:
            print(f"[FLASK_CTRL] Defend failed: {result.get('error')}")
        
        return jsonify({**result, **self.engine.consume_ui_state()})

    def draw(self):
        defender = self.engine.state.defender
        print(f"[FLASK_CTRL] Draw request - Phase: {self.engine.state.phase}, Defender: {defender}")
        
        result = self.engine.defender_draw(defender)
        
        # Only run AI if draw was successful
        if not result.get('error'):
            self._run_ai_if_needed()
        
        return jsonify({**result, **self.engine.consume_ui_state()})

    def rule_8_drop(self, value):
        attacker = self.engine.state.attacker
        result = self.engine.rule_8_drop(attacker, value)
        return jsonify({**result, **self.engine.consume_ui_state()})

    def rule_8_crash(self, crash):
        defender = self.engine.state.defender
        result = self.engine.rule_8_crash(defender, crash)
        self._run_ai_if_needed()
        return jsonify({**result, **self.engine.consume_ui_state()})
    
    def _run_ai_if_needed(self):
        self.ai.play_if_needed()

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
