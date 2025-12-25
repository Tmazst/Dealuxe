import uuid
import time

from game.engine import CardGameEngine
from game.models import Player


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

    def create_game(self, mode="human_vs_ai"):
        """
        Creates a new game session and returns game_id.
        """

        game_id = str(uuid.uuid4())

        if mode == "human_vs_ai":
            players = [
                Player("Human"),
                Player("Computer")
            ]

        elif mode == "local":
            players = [
                Player("Player 1"),
                Player("Player 2")
            ]

        else:
            raise ValueError(f"Unsupported game mode: {mode}")

        engine = CardGameEngine(players)

        self.games[game_id] = {
            "engine": engine,
            "mode": mode,
            "created_at": time.time(),
            "status": "active"
        }

        print(f"[MANAGER] Created game {game_id} ({mode})")

        return game_id

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
