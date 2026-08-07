"""
*** NOT USED BY THE RUNNING APP -- KEPT FOR REFERENCE ONLY ***

app.py wires up `game.manager_redis.GameManager` as the single, real
GameManager instance (see `manager = GameManager()` in app.py, importing
from game.manager_redis). That instance is what's passed everywhere
(controllers/multiplayer_controller.py, flask routes, etc.) as `game_manager`.

This file's GameManager (in-memory only, no Redis) is never instantiated
anywhere in the codebase. `manager_redis.py` already contains its own
in-memory fallback for when Redis is unreachable, so this file is fully
redundant with it.

`controllers/multiplayer_controller.py` used to have a stray, unused
`from game.manager import GameManager` import referencing this file -- that
import did nothing (the real manager is always passed in as a parameter),
and has been removed there to avoid implying this file is live.

Confirmed via `grep -rn "game.manager import" .` across the whole repo
(2026-07-27 audit) -- no other importers besides that removed one.

Left in place rather than deleted per project decision -- do not wire this
back in without also removing/merging manager_redis.py, or the app will have
two independent, out-of-sync GameManagers again.
"""

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
