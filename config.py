"""
Game Configuration
Centralized settings for the Dealuxe card game
"""
import random
from datetime import timedelta

class GameConfig:
    """Core game configuration"""
    
    # Free play settings
    FREE_CASH_MIN = 1000
    FREE_CASH_MAX = 2000
    FREE_CASH_DURATION_HOURS = 24
    FREE_CASH_TARGET_MIN = 8000
    FREE_CASH_TARGET_MAX = 12000
    
    # Game settings
    DEFAULT_CARD_COUNT = 6
    ALLOWED_CARD_COUNTS = [6, 8, 10]
    
    # Opponent types
    OPPONENT_AI = 'ai'
    OPPONENT_HUMAN = 'human'
    
    # Bet types
    BET_TYPE_REAL = 'real'
    BET_TYPE_FAKE = 'fake'
    
    # Session status
    SESSION_ACTIVE = 'active'
    SESSION_COMPLETED = 'completed'
    SESSION_CANCELLED = 'cancelled'
    
    @staticmethod
    def get_random_free_cash():
        """Generate random free cash amount within configured range"""
        return random.randint(GameConfig.FREE_CASH_MIN, GameConfig.FREE_CASH_MAX)
    
    @staticmethod
    def get_random_free_target():
        """Generate random target amount for free cash challenge"""
        return random.randint(GameConfig.FREE_CASH_TARGET_MIN, GameConfig.FREE_CASH_TARGET_MAX)
    
    @staticmethod
    def get_free_cash_expiry():
        """Get expiry duration for free cash"""
        return timedelta(hours=GameConfig.FREE_CASH_DURATION_HOURS)


class DatabaseConfig:
    """Database configuration"""
    DATABASE_PATH = 'dealuxe_game.db'
    ECHO_SQL = False  # Set to True for debugging
