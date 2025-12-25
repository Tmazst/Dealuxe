class CLIController:
    def __init__(self, engine):
        self.engine = engine

    # -----------------------------
    # DISPLAY HELPERS
    # -----------------------------

    def show_state(self):
        state = self.engine.get_state()

        print("\n===== GAME STATE =====")
        print("Phase:", state["phase"])
        print("Attacker:", state["attacker"])
        print("Defender:", state["defender"])
        print("Attack card:", state["attack_card"])

        for pid, hand in state["hands"].items():
            print(f"Player {pid} hand:", hand)

        print("======================\n")

    # -----------------------------
    # MAIN GAME LOOP
    # -----------------------------

    def run(self):
        print("=== CARD GAME CLI ===")

        while not self.engine.state.game_over:
            self.engine.start_turn()
            self.show_state()

            phase = self.engine.state.phase

            if phase == "ATTACK":
                self.handle_attack()

            elif phase == "DEFENSE":
                self.handle_defense()

            elif phase == "RULE_8":
                self.handle_rule_8()

            elif phase == "GAME_OVER":
                break

        print(f"\nGAME OVER. Winner: Player {self.engine.state.winner}")

    # -----------------------------
    # ATTACK PHASE
    # -----------------------------

    def handle_attack(self):
        attacker = self.engine.state.attacker
        hand = self.engine.players[attacker].hand

        print(f"{self.engine.players[attacker].name}: Choose an attack card (4–13):")
        for i, card in enumerate(hand):
            print(f"[{i}] {card}")

        while True:
            choice = input("> ").strip()
            if not choice.isdigit():
                print("Enter a valid index.")
                continue
            idx = int(choice)
            # Validate index locally before calling engine
            if idx < 0 or idx >= len(hand):
                print("Index out of range.")
                continue

            result = self.engine.attack(attacker, idx)
            if "error" in result:
                print(result["error"])
                continue

            break

    # -----------------------------
    # DEFENSE PHASE
    # -----------------------------

    def handle_defense(self):
        defender = self.engine.state.defender
        hand = self.engine.players[defender].hand

        print("Defend: choose two cards (comma separated) or press Enter to draw:")
        for i, card in enumerate(hand):
            print(f"[{i}] {card}")

        choice = input("> ").strip()

        if choice == "":
            self.engine.defender_draw(defender)
            return

        try:
            i1, i2 = map(int, choice.split(","))
            result = self.engine.defend(defender, i1, i2)

            if "error" in result:
                print(result["error"])
                return

        except ValueError:
            print("Invalid input format.")

    # -----------------------------
    # RULE 8 PHASE
    # -----------------------------

    def handle_rule_8(self):
        attacker = self.engine.state.attacker
        defender = self.engine.state.defender

        print("RULE 8: Drop a value (1, 2, or 3):")
        choice = input("> ").strip()

        if not choice.isdigit():
            print("Invalid input.")
            return

        drop = self.engine.rule_8_drop(attacker, int(choice))

        if "error" in drop:
            print(drop["error"])
            return

        # Defender may crash
        defender_hand = self.engine.players[defender].hand
        can_crash = any(c.value == int(choice) for c in defender_hand)

        if can_crash:
            crash = input("Defender: crash trail? (y/n): ").strip().lower()
            self.engine.rule_8_crash(defender, crash == "y")
