import uuid
import time
import pickle
import redis
import os

from game.engine import CardGameEngine
from game.models import Player


class GameManager:
    """
    Redis-backed game session manager for multi-worker deployments.
    Falls back to in-memory storage if Redis is unavailable (development).
    """

    def __init__(self):
        # Try to connect to Redis
        try:
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=False,  # We'll use pickle for serialization
                socket_connect_timeout=2
            )
            # Test connection
            self.redis_client.ping()
            self.use_redis = True
            print(f"[MANAGER] Connected to Redis at {redis_host}:{redis_port}")
        except Exception as e:
            print(f"[MANAGER] Redis connection failed: {e}. Using in-memory storage.")
            self.use_redis = False
            self.games = {}

    # -----------------------------
    # CREATE GAME
    # -----------------------------

    def create_game(self, mode="human_vs_ai"):
        """
        Creates a new game session and returns game_id.
        """
        game_id = str(uuid.uuid4())
        players = None

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

        session_data = {
            "engine": engine,
            "mode": mode,
            "created_at": time.time(),
            "status": "active",
            "players": players
        }

        # Store in Redis or in-memory
        if self.use_redis:
            try:
                # Serialize the entire session with pickle
                serialized = pickle.dumps(session_data)
                # Store with 24-hour expiration
                self.redis_client.setex(f"game:{game_id}", 86400, serialized)
                print(f"[MANAGER] Created game {game_id} in Redis ({mode})")
            except Exception as e:
                print(f"[MANAGER] Failed to store in Redis: {e}")
                raise
        else:
            self.games[game_id] = session_data
            print(f"[MANAGER] Created game {game_id} in memory ({mode})")

        return game_id, session_data

    # -----------------------------
    # GET GAME
    # -----------------------------

    def get_game(self, game_id):
        """
        Retrieves game engine from Redis or in-memory storage.
        """
        if self.use_redis:
            try:
                serialized = self.redis_client.get(f"game:{game_id}")
                if not serialized:
                    raise KeyError(f"Game {game_id} not found in Redis")
                session_data = pickle.loads(serialized)
                return session_data["engine"]
            except Exception as e:
                print(f"[MANAGER] Failed to retrieve game from Redis: {e}")
                raise KeyError(f"Game not found: {game_id}")
        else:
            session = self.games.get(game_id)
            if not session:
                raise KeyError(f"Game {game_id} not found")
            return session["engine"]

    # -----------------------------
    # UPDATE GAME (Important!)
    # -----------------------------

    def update_game(self, game_id, engine):
        """
        Updates the game state in storage after modifications.
        MUST be called after any game state changes!
        """
        if self.use_redis:
            try:
                # Re-fetch to get full session data
                serialized = self.redis_client.get(f"game:{game_id}")
                if serialized:
                    session_data = pickle.loads(serialized)
                    session_data["engine"] = engine
                    # Re-serialize and store
                    self.redis_client.setex(f"game:{game_id}", 86400, pickle.dumps(session_data))
                else:
                    print(f"[MANAGER] Warning: Game {game_id} not found for update")
            except Exception as e:
                print(f"[MANAGER] Failed to update game in Redis: {e}")
        else:
            if game_id in self.games:
                self.games[game_id]["engine"] = engine

    # -----------------------------
    # DELETE GAME
    # -----------------------------

    def delete_game(self, game_id):
        if self.use_redis:
            self.redis_client.delete(f"game:{game_id}")
            print(f"[MANAGER] Deleted game {game_id} from Redis")
        else:
            if game_id in self.games:
                del self.games[game_id]
                print(f"[MANAGER] Deleted game {game_id} from memory")

    # -----------------------------
    # LIST GAMES (DEBUG / ADMIN)
    # -----------------------------

    def list_games(self):
        if self.use_redis:
            keys = self.redis_client.keys("game:*")
            games = {}
            for key in keys:
                game_id = key.decode('utf-8').split(':')[1]
                try:
                    serialized = self.redis_client.get(key)
                    data = pickle.loads(serialized)
                    games[game_id] = {
                        "mode": data["mode"],
                        "status": data["status"],
                        "age": time.time() - data["created_at"]
                    }
                except:
                    pass
            return games
        else:
            return {
                gid: {
                    "mode": data["mode"],
                    "status": data["status"],
                    "age": time.time() - data["created_at"]
                }
                for gid, data in self.games.items()
            }
