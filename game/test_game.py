import random
from collections import Counter

# -----------------------------
# CARD & DECK SETUP
# -----------------------------

class Card:
    """
    Represents a single playing card.
    """
    def __init__(self, rank, suit, value):
        self.rank = rank      # '2'...'10','J','Q','K','A'
        self.suit = suit      # ♥ ♦ ♣ ♠
        self.value = value    # numeric value used for sums

    def __repr__(self):
        return f"{self.rank}{self.suit}"


class Deck:
    """
    Represents the 52-card batch with suits and face cards.
    """
    def __init__(self):
        self.cards = []

        suits = ['♥', '♦', '♣', '♠']

        ranks = [('A', 1),('2', 2),('3', 3),('4', 4),('5', 5),('6', 6),('7', 7),
            ('8', 8),('9', 9),('10', 10),('J', 11),('Q', 12),('K', 13),]

        for suit in suits:
            for rank, value in ranks:
                self.cards.append(Card(rank, suit, value))

        random.shuffle(self.cards)
        print("Deck initialized and shuffled: ", self.cards)

    def draw(self):
        if not self.cards:
            return None
        return self.cards.pop()


# -----------------------------
# PLAYER
# -----------------------------

class Player:
    def __init__(self, name):
        self.name = name
        self.hand = []

    def draw_card(self, deck):
        """
        Player grabs a card from the batch.
        """
        card = deck.draw()
        if card:
            self.hand.append(card)
            print(f"{self.name} draws {card} value: {card.value}") #flash
        return card

    def show_hand(self):
        """
        Display cards grouped by value (suits ignored for counting).
        """
        counts = Counter(card.value for card in self.hand)
        return dict(counts)
    
    def show_hand_verbose(self):
        """
        Display full cards including suits.
        """
        return [str(card) for card in self.hand]

    def remove_cards(self, cards):
        """
        Remove specific cards from hand.
        """
        for c in cards:
            self.hand.remove(c)


# -----------------------------
# GAME LOGIC
# -----------------------------
#Rule No.8 Logic
def handle_rule_8(self, attacker, defender):
    print("\n=== RULE 8: TRAIL PHASE ===")
    print(f"{attacker.name} may attempt to finish the game.")

    while len(attacker.hand) > 3:
        print("\nAttacker hand:", attacker.show_hand_verbose())

        # Choose trail value
        choice = input("Choose a value to trail (1, 2, or 3): ").strip()

        if choice not in ("1", "2", "3"):
            print("Invalid choice.")
            continue

        trail_value = attacker.hand[int(choice)]

        # Check attacker has this value
        trail_cards = [c for c in attacker.hand if c.value == trail_value]
        if not trail_cards:
            print(f"You do not have a {trail_value}.")
            continue

        # Drop ONE card
        dropped_card = trail_cards[0]
        attacker.hand.remove(dropped_card)
        print(f"{attacker.name} drops {dropped_card}")

        # WIN CHECK
        # if is_winner(attacker):
        #     print(f"{attacker.name} wins!")
        #     self.game_over = True
        #     return

        # Check if defender can crash
        defender_cards = [c for c in defender.hand if c.value == trail_value]

        if defender_cards:
            print(f"{defender.name} can crash the trail with a {trail_value} if available. If not you may draw a card to attempt")
            crash = input("Stop attacker's trail to win, drop the same card value to crash: ").strip().lower()

            if defender.hand[int(crash)] == trail_value:
                print(f"{defender.name} crashes the trail!")
                drawn = attacker.draw_card(self.deck)
                if drawn is None:
                    print("Batch empty. No card drawn.")
                print("Trail failed. Returning to normal play.")
                return True
            else:
                print(f"{defender.name} allows the trail to continue.")
                drawn = defender.draw_card(self.deck)

            # Safety net (should not normally reach here)
            if is_winner(attacker):
                print(f"{attacker.name} wins!")
                self.game_over = True


def is_low_only(player):
    return all(card.value in (1,2,3) for card in player.hand)

def has_attack_card(player):
    return any(4 <= card.value <= 13 for card in player.hand)

def is_winner(player):
    return len(player.hand) <= 3 and is_low_only(player)


class CardGame:
    def __init__(self):
        self.deck = Deck()
        self.players = [Player("Player 1"), Player("Player 2")]

        # Deal 6 cards each (you can adjust later)
        for _ in range(6):
            for p in self.players:
                p.draw_card(self.deck)

        self.current_player_index = 0


    def find_sum_pair(self, hand, target_card):
        """
        Find two cards in hand whose VALUES sum to target_card.value.
        Returns a tuple of Card objects or None.
        """

        # Count how many cards we have per value
        value_counts = Counter(card.value for card in hand)

        for value_a in value_counts:
            value_b = target_card.value - value_a

            if value_b in value_counts:
                # Handle cases like 3 + 3 = 6 (need at least two 3s)
                if value_a != value_b or value_counts[value_a] > 1:

                    # Retrieve actual Card objects from the hand
                    card_a = next(card for card in hand if card.value == value_a)

                    if value_a == value_b:
                        card_b = next(
                            card for card in hand
                            if card.value == value_b and card is not card_a
                        )
                    else:
                        card_b = next(card for card in hand if card.value == value_b)

                    return (card_a, card_b)

        return None


    def play_turn(self):
        attacker = self.players[self.current_player_index]
        defender = self.players[1 - self.current_player_index]

        print("\n--------------------------------")
        print(f"{attacker.name}'s turn")
        print("Attacker hand:", attacker.show_hand_verbose())

        # GLOBAL WIN CHECK (very important)
        if is_winner(attacker):
            print(f"{attacker.name} wins!")
            return True  # signal game over

        # RULE 8 CHECK (priority over normal attack)
        if not has_attack_card(attacker) and is_low_only(attacker) and len(attacker.hand) > 3:
            print(f"{attacker.name} enters Rule 8 (trail phase)")
            # the 8 rule logic will return True if defender crashed trail 
            crashed = self.handle_rule_8(attacker, defender)
            if crashed:
                # SWITCH TURN TO DEFENDER'S FAVOR
                self.current_player_index ^= 1
            return False

        # NORMAL ATTACK FLOW
        attack_cards = [c for c in attacker.hand if 4 <= c.value <= 13]

        if not attack_cards:
            print(f"{attacker.name} has not attack card, enters Rule 8 (trail phase)")
            self.handle_rule_8(attacker, defender)
            if crashed:
                # SWITCH TURN TO DEFENDER'S FAVOR
                self.current_player_index ^= 1
            return False
        #     # No attack and not eligible for Rule 8 → forced draw
        #     print(f"{attacker.name} has no attack card and cannot trail. Drawing one card.")
        #     attacker.draw_card(self.deck)
        #     self.current_player_index ^= 1
        #     return False


        self.attack_card=None
        def attacker_turn(show_hand=False):
            while True:
                # Recompute allowed attack cards from the current hand
                available_attacks = [c for c in attacker.hand if 4 <= c.value <= 13]

                if show_hand:
                    print(f"{attacker.name}'s turn again")
                    print("Attacker hand:", attacker.show_hand_verbose())

                if not available_attacks:
                    print("No available attack cards.")
                    return None

                # MANUAL ATTACK CARD SELECTION (show only attackable cards)
                print("Choose an ATTACK card:")
                for i, card in enumerate(available_attacks):
                    print(f"[{i}] {card}")

                choice = input("Enter index: ").strip()
                if choice.isdigit() and int(choice) < len(available_attacks):
                    attack_card = available_attacks[int(choice)]
                    break
                print("Invalid choice.")

            # remove the selected card from the current hand
            attacker.hand.remove(attack_card)
            self.attack_card = attack_card
            print(f"{attacker.name} drops {attack_card}")
        attacker_turn()

        # DEFENDER LOOP
        while True:
            print("\nDefender hand:", defender.show_hand_verbose())

            # Check defender win (important edge case)
            if is_winner(defender):
                print(f"{defender.name} wins!")
                return True

            print("Choose two cards that sum to", self.attack_card.value)
            print("Enter indexes separated by space, or press Enter to draw:")

            for i, card in enumerate(defender.hand):
                print(f"[{i}] {card}")

            choice = input("> ").strip()

            if choice == "":
                drawn = defender.draw_card(self.deck)
                if drawn is None:
                    print("Batch empty. Defense failed.")
                    break
                if is_winner(self.attack_card):
                    print(f"{attacker.name} wins! you failed to defend")
                    break
                print(f" Defender draws card {drawn}, turn turns back to attacker")
                attacker_turn(show_hand=True)

            try:
                print("Choices: ",choice)
                _i1, _i2 = choice.split(",")
                i1 = int(_i1)
                i2 = int(_i2)
                c1 = defender.hand[i1] #pick the cards from defenders hand
                c2 = defender.hand[i2]

                if c1.value + c2.value != self.attack_card.value:
                    print("Values do not sum correctly.")
                    continue

                defender.hand.remove(c1)
                defender.hand.remove(c2)
                print(f"{defender.name} drops {c1} + {c2}")

                # WIN CHECK AFTER DEFENSE
                if is_winner(defender):
                    print(f"{defender.name} wins!")
                    break

                break

            except (ValueError, IndexError):
                print(f"Invalid input: {ValueError} Index: {IndexError}")
                continue

        # SWITCH TURN
        self.current_player_index ^= 1
        # return False


    def run(self, rounds=10):
        print("""
        Temporary loop runner.
        Winning rules come later.
        """)
        for _ in range(rounds):
            self.play_turn()


# -----------------------------
# ENTRY POINT
# -----------------------------

# if __name__ == "__main__":
game = CardGame()
game.run()
