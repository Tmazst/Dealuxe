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
