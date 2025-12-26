import random
from collections import Counter

# -----------------------------
# CARD
# -----------------------------

class Card:
    def __init__(self, rank, suit, value):
        self.rank = rank
        self.suit = suit
        self.value = value

    def __repr__(self):
        return f"{self.rank}{self.suit}"


# -----------------------------
# DECK
# -----------------------------

class Deck:
    def __init__(self):
        self.cards = []

        suits = ['♥', '♦', '♣', '♠']
        ranks = [
            ('A', 1), ('2', 2), ('3', 3), ('4', 4), ('5', 5),
            ('6', 6), ('7', 7), ('8', 8), ('9', 9), ('10', 10),
            ('J', 11), ('Q', 12), ('K', 13)
        ]

        for suit in suits:
            for rank, value in ranks:
                self.cards.append(Card(rank, suit, value))

        random.shuffle(self.cards)
        print("[MODELS] Deck initialized")

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
        card = deck.draw()
        if card:
            self.hand.append(card)
            print(f"[PLAYER] {self.name} draws a card")
        return card

    def show_hand_verbose(self):
        return [str(c) for c in self.hand]

    def show_hand(self):
        counts = Counter(c.value for c in self.hand)
        return dict(counts)


# -----------------------------
# GAME STATE
# -----------------------------

class GameState:
    """
    Holds mutable game state.
    """
    def __init__(self):
        self.phase = "ATTACK"   # ATTACK, DEFENSE, RULE_8, GAME_OVER
        self.attacker = 0
        self.defender = 1
        self.mode = "human_vs_ai"
        self.attack_card = None
        self.trail_value = None
        self.game_over = False
        self.winner = None
        self.defence_cards=None
        self.defender_drawn_card=None


