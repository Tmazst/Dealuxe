"""
Game Configuration
Centralized settings for the Dealuxe card game
"""
import os
import random
from datetime import timedelta

class GameConfig:
    """Core game configuration"""
    
    # User account / KYC uploads
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'instance', 'uploads'
    )
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max upload
    ALLOWED_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    
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


class PaymentConfig:
    """MojaPOS payment gateway configuration.

    Values may come from class defaults or environment variables. The
    downstream `MojaPOSService` reads these through Flask's app config, so
    `app.config.from_object(PaymentConfig)` (or an equivalent mapping) is
    expected at startup.
    """

    # MojaPOS API base URL. Use the sandbox endpoint in development.
    MOJAPOS_API_URL = os.environ.get(
        'MOJAPOS_API_URL',
        'https://sandbox.mojapos.com/v1'
    )

    # MojaPOS credentials (keep out of source control in production).
    MOJAPOS_API_KEY = os.environ.get('MOJAPOS_API_KEY', '')
    MOJAPOS_MERCHANT_ID = os.environ.get('MOJAPOS_MERCHANT_ID', '')
    MOJAPOS_SECRET_KEY = os.environ.get('MOJAPOS_SECRET_KEY', '')

    # Publicly reachable callback URL (must be HTTPS in production).
    MOJAPOS_CALLBACK_URL = os.environ.get(
        'MOJAPOS_CALLBACK_URL',
        'https://dealuxe.games/api/payment/callback'
    )

    # Shared secret used to verify inbound MojaPOS callback signatures.
    MOJAPOS_WEBHOOK_SECRET = os.environ.get('MOJAPOS_WEBHOOK_SECRET', '')

    # Local-debit mock path toggle. When True, tournament entry is charged
    # directly from the wallet (sandbox/mock) instead of the real gateway.
    MOJAPOS_MOCK_MODE = os.environ.get('MOJAPOS_MOCK_MODE', 'true').lower() in (
        '1', 'true', 'yes', 'on'
    )
