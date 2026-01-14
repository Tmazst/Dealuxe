import uuid
import time

from game.engine import CardGameEngine
from game.models import Player
from database import Player as db_player
# from flask import session

class GameManager:
    """
    Responsible for creating, storing, and managing game sessions.
    """

    def __init__(self):
        # game_id -> session data
        self.games = {}

    # -----------------------------
    # CREATE GAME
    # -----------------------------

    def create_game(self, mode="human_vs_ai", card_count=6):
        """
        Creates a new game session and returns game_id.
        """

        game_id = str(uuid.uuid4())
        players=None

        if mode == "human_vs_ai":
            players = [
                Player("human"),
                Player("Computer")
            ]
            print("[MANANGER] Game Mode: human_vs_ai")
        elif mode == "local":
            players = [
                Player("Player 1"),
                Player("Player 2")
            ]
            print("[MANANGER] Game Mode: LOCAL")

        else:
            raise ValueError(f"Unsupported game mode: {mode}")

        engine = CardGameEngine(players, cards_per_player=card_count)

        self.games[game_id] = {
            "engine": engine,
            "mode": mode,
            "created_at": time.time(),
            "status": "active",
            "players": players
        }

        print(f"[MANAGER] Created game {game_id} ({mode})")
        game_details=self.games[game_id]
        # Don't print game_details as it contains player objects with card data

        return game_id, game_details

    # -----------------------------
    # GET GAME
    # -----------------------------

    def get_game(self, game_id):
        session = self.games.get(game_id)

        if not session:
            raise KeyError("Game not found")

        return session["engine"]

    # -----------------------------
    # DELETE GAME
    # -----------------------------

    def delete_game(self, game_id):
        if game_id in self.games:
            del self.games[game_id]
            print(f"[MANAGER] Deleted game {game_id}")

    # -----------------------------
    # LIST GAMES (DEBUG / ADMIN)
    # -----------------------------

    def list_games(self):
        return {
            gid: {
                "mode": data["mode"],
                "status": data["status"],
                "age": time.time() - data["created_at"]
            }
            for gid, data in self.games.items()
        }
