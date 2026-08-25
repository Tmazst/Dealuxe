"""
Game Configuration
Centralized settings for the Dealuxe card game
"""
import os
import random
import secrets
from datetime import timedelta


TRUE_VALUES = {'1', 'true', 'yes', 'on'}
LOCAL_ENVIRONMENTS = {'development', 'dev', 'local', 'test', 'testing'}


def _env_bool(environ, key, default=False):
    """Read a boolean environment setting without truthy-string mistakes."""
    raw_value = environ.get(key)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in TRUE_VALUES


def build_pilot_economy_config(environ=None):
    """Build the Version 3 pilot flags and reject unsafe combinations."""
    environ = os.environ if environ is None else environ
    pilot_mode = _env_bool(environ, 'PILOT_MODE', default=False)
    paid_entry = _env_bool(environ, 'PAID_TOURNAMENT_ENTRY_ENABLED', default=False)
    cash_prizes = _env_bool(environ, 'CASH_PRIZES_ENABLED', default=False)
    pilot_credits = _env_bool(environ, 'PILOT_CREDITS_ENABLED', default=pilot_mode)
    cup_enabled = _env_bool(environ, 'CUP_ENABLED', default=False)
    cup_qualification = _env_bool(
        environ, 'CUP_QUALIFICATION_ENABLED', default=pilot_mode
    )
    cup_cash_payouts = _env_bool(environ, 'CUP_CASH_PAYOUTS_ENABLED', default=False)

    if pilot_mode and paid_entry:
        raise RuntimeError('Paid tournament entry cannot be enabled in PILOT_MODE')
    if pilot_mode and cash_prizes:
        raise RuntimeError('Cash prizes cannot be enabled in PILOT_MODE')
    if pilot_mode and not pilot_credits:
        raise RuntimeError('PILOT_CREDITS_ENABLED is required in PILOT_MODE')
    if cup_cash_payouts:
        raise RuntimeError('CUP_CASH_PAYOUTS_ENABLED is not available in Version 3')

    return {
        'PILOT_MODE': pilot_mode,
        'PAID_TOURNAMENT_ENTRY_ENABLED': paid_entry,
        'CASH_PRIZES_ENABLED': cash_prizes,
        'PILOT_CREDITS_ENABLED': pilot_credits,
        'PILOT_TOURNAMENT_ENTRY_COST': 10.0,
        'CUP_ENABLED': cup_enabled,
        'CUP_QUALIFICATION_ENABLED': cup_qualification,
        'CUP_CASH_PAYOUTS_ENABLED': cup_cash_payouts,
        'CUP_EVENT_KEY': str(environ.get('CUP_EVENT_KEY') or 'umshova-cup-pilot').strip(),
        'CUP_SEASON': str(environ.get('CUP_SEASON') or '2026').strip(),
        'CUP_CAPACITY': 64,
    }


def build_hybrid_config(environ=None):
    """Build the disabled-by-default Hybrid MVP feature configuration."""
    environ = os.environ if environ is None else environ
    master = _env_bool(environ, 'HYBRID_ENABLED', default=False)
    profile = _env_bool(environ, 'HYBRID_PROFILE_ENABLED', default=False)
    matching = _env_bool(environ, 'HYBRID_MATCHING_ENABLED', default=False)
    chat = _env_bool(environ, 'HYBRID_CHAT_ENABLED', default=False)
    bracket_discovery = _env_bool(
        environ, 'HYBRID_BRACKET_DISCOVERY_ENABLED', default=False
    )
    payments = _env_bool(environ, 'HYBRID_PAYMENTS_ENABLED', default=False)
    relationship = _env_bool(
        environ, 'HYBRID_RELATIONSHIP_ENABLED', default=False
    )
    children = {
        'HYBRID_PROFILE_ENABLED': profile,
        'HYBRID_MATCHING_ENABLED': matching,
        'HYBRID_CHAT_ENABLED': chat,
        'HYBRID_BRACKET_DISCOVERY_ENABLED': bracket_discovery,
        'HYBRID_PAYMENTS_ENABLED': payments,
        'HYBRID_RELATIONSHIP_ENABLED': relationship,
    }
    enabled_children = [name for name, enabled in children.items() if enabled]
    if enabled_children and not master:
        raise RuntimeError(
            'HYBRID_ENABLED is required when enabling: '
            + ', '.join(enabled_children)
        )
    if relationship:
        raise RuntimeError('HYBRID_RELATIONSHIP_ENABLED is unavailable in the MVP')
    if payments:
        raise RuntimeError('HYBRID_PAYMENTS_ENABLED requires post-pilot approval')
    if matching or chat or bracket_discovery:
        raise RuntimeError(
            'Hybrid matching, chat and bracket discovery are not implemented '
            'in the foundation slice'
        )
    return {
        'HYBRID_ENABLED': master,
        **children,
    }


def _split_origins(raw_value):
    """Return a normalized, de-duplicated Socket.IO origin allowlist."""
    origins = []
    for value in str(raw_value or '').split(','):
        origin = value.strip().rstrip('/')
        if origin and origin not in origins:
            origins.append(origin)
    return origins


def build_runtime_security_config(environ=None):
    """Build and validate security-sensitive runtime configuration.

    Local development receives a process-local session secret when one is not
    supplied. Non-local environments fail closed instead of silently using a
    committed/default secret, wildcard origins, an implicit Redis endpoint, or
    an unverified live payment callback.
    """
    environ = os.environ if environ is None else environ
    environment = str(
        environ.get('APP_ENV')
        or environ.get('FLASK_ENV')
        or environ.get('ENV')
        or 'development'
    ).strip().lower()
    is_local = environment in LOCAL_ENVIRONMENTS

    secret_key = str(environ.get('FLASK_SECRET_KEY') or '').strip()
    generated_secret = False
    if not secret_key:
        if not is_local:
            raise RuntimeError('FLASK_SECRET_KEY is required outside local development')
        secret_key = secrets.token_urlsafe(48)
        generated_secret = True

    default_origins = 'http://127.0.0.1:5000,http://localhost:5000' if is_local else ''
    socketio_origins = _split_origins(
        environ.get('SOCKETIO_ALLOWED_ORIGINS', default_origins)
    )
    if not socketio_origins:
        raise RuntimeError('SOCKETIO_ALLOWED_ORIGINS must contain at least one origin')
    if '*' in socketio_origins:
        raise RuntimeError('Wildcard Socket.IO origins are not allowed')

    redis_url = str(environ.get('REDIS_URL') or '').strip()
    if not redis_url:
        if not is_local:
            raise RuntimeError('REDIS_URL is required outside local development')
        redis_url = 'redis://127.0.0.1:6379/0'

    payment_mock_mode = _env_bool(environ, 'MOJAPOS_MOCK_MODE', default=False)
    verify_webhooks = _env_bool(
        environ, 'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE', default=False
    )
    webhook_secret = str(environ.get('MOJAPOS_WEBHOOK_SECRET') or '').strip()
    if not is_local and not payment_mock_mode:
        if not verify_webhooks:
            raise RuntimeError(
                'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE must be enabled for live payments'
            )
        if not webhook_secret:
            raise RuntimeError(
                'MOJAPOS_WEBHOOK_SECRET is required when live webhook verification is enabled'
            )

    return {
        'APP_ENV': environment,
        'IS_LOCAL_ENVIRONMENT': is_local,
        'SECRET_KEY': secret_key,
        'SESSION_SECRET_GENERATED': generated_secret,
        'SOCKETIO_ALLOWED_ORIGINS': socketio_origins,
        'REDIS_URL': redis_url,
    }

class GameConfig:
    """Core game configuration"""
    
    # User account / KYC uploads
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'instance', 'uploads'
    )
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max upload
    ALLOWED_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    
    # Registered-user promotional credits (Version 3 pilot wallet).
    PROMOTIONAL_CREDIT_REGISTRATION_AMOUNT = 10.0
    PROMOTIONAL_CREDIT_DURATION_DAYS = 30

    # Guest/in-memory practice settings. These remain separate from the
    # registered user's promotional-credit wallet.
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

    @staticmethod
    def get_registration_promotional_credit():
        """Return the fixed Version 3 registration-credit grant."""
        return float(GameConfig.PROMOTIONAL_CREDIT_REGISTRATION_AMOUNT)

    @staticmethod
    def get_promotional_credit_expiry():
        """Return the approved 30-day promotional-credit lifetime."""
        return timedelta(days=GameConfig.PROMOTIONAL_CREDIT_DURATION_DAYS)


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

    # Verify inbound webhook signatures. OFF until MojaPOS's webhook signing
    # scheme is confirmed; set true (with MOJAPOS_WEBHOOK_SECRET) when known.
    MOJAPOS_VERIFY_WEBHOOK_SIGNATURE = os.environ.get(
        'MOJAPOS_VERIFY_WEBHOOK_SIGNATURE', 'false'
    ).lower() in ('1', 'true', 'yes', 'on')

    # Local-debit mock path toggle. REAL by default: mock mode only runs when
    # this is EXPLICITLY set to true (e.g. MOJAPOS_MOCK_MODE=true). Any unset /
    # false value (or a VPS that cannot read .env) goes straight to the gateway.
    MOJAPOS_MOCK_MODE = os.environ.get('MOJAPOS_MOCK_MODE', 'false').lower() in (
        '1', 'true', 'yes', 'on'
    )


class LogConfig:
    """Backend print-log capture settings (viewable in the admin dashboard)."""
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    PRINT_LOG_FILE = os.path.join(LOG_DIR, 'print_logs.txt')
    PRINT_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB cap; file is truncated when exceeded
