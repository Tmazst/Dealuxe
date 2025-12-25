import random

SUITS = ["hearts", "diamonds", "clubs", "spades"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

class Deck:
    def __init__(self):
        self.cards = [
            {"suit": suit, "rank": rank}
            for suit in SUITS
            for rank in RANKS
        ]

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self, count=1):
        if len(self.cards) < count:
            raise ValueError("Not enough cards left")
        drawn = self.cards[:count]
        self.cards = self.cards[count:]
        return drawn
