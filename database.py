"""
Database Configuration and Models
SQLAlchemy setup for Dealuxe Card Game
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()


def _table_has_column(table_name, column_name):
    """Check whether an SQLite table already includes a column."""
    if db.engine is None:
        return False
    if db.engine.name != 'sqlite':
        return True

    with db.engine.connect() as connection:
        rows = connection.execute(text(f'PRAGMA table_info({table_name})')).fetchall()
    return any(row[1] == column_name for row in rows)


def ensure_tournament_schema():
    """Add missing columns to existing tables when the database already exists.

    SQLAlchemy's ``db.create_all()`` never alters existing tables, so every
    new column added to the models after a database was first created must be
    listed here or legacy databases (e.g. a pre-existing VPS install) will fail
    with ``no such column``.
    """
    if db.engine is None:
        return

    if db.engine.name != 'sqlite':
        return

    # with db.session.begin():
    #     for table_name, column_definition in [
    #         ('users', 'is_super_admin BOOLEAN DEFAULT 0'),
    #         ('bet_sessions', 'tournament_id INTEGER'),
    #         ('game_rooms', 'tournament_id INTEGER'),
    #         ('game_rooms', 'match_id INTEGER'),
    #         ('game_rooms', 'is_tournament_game BOOLEAN DEFAULT 0'),
    #         ('transactions', 'tournament_id INTEGER'),
    #         ('tournament_participants', 'lock_voted BOOLEAN DEFAULT 0'),
    #     ]:
    #         column_name = column_definition.split()[0]
    #         if not _table_has_column(table_name, column_name):
    #             db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_definition}'))

    #     for index_sql in [
    #         'CREATE INDEX IF NOT EXISTS idx_bet_sessions_tournament_id ON bet_sessions (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_game_rooms_tournament_id ON game_rooms (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_game_rooms_match_id ON game_rooms (match_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_transactions_tournament_id ON transactions (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournaments_status ON tournaments (status)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournaments_tournament_type ON tournaments (tournament_type)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_participants_tournament_id ON tournament_participants (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_participants_user_id ON tournament_participants (user_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_participants_status ON tournament_participants (status)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_brackets_tournament_id ON tournament_brackets (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_matches_tournament_id ON tournament_matches (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_matches_status ON tournament_matches (status)',
    #         'CREATE INDEX IF NOT EXISTS idx_tournament_prize_pools_tournament_id ON tournament_prize_pools (tournament_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_user_id ON withdrawal_requests (user_id)',
    #         'CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_status ON withdrawal_requests (status)',
    #     ]:
    #         db.session.execute(text(index_sql))


def ensure_user_account_schema():
    """Add user-account / KYC columns to an existing ``users`` table.

    ``db.create_all()`` never alters existing tables, so databases created
    before these columns existed need ALTER TABLE (SQLite path shown; the
    users table is small so this runs at startup inside init_db).
    """
    if db.engine is None:
        return
    if db.engine.name != 'sqlite':
        return

    user_columns = [
        ('country', 'VARCHAR(50)'),
        ('address', 'VARCHAR(200)'),
        ('date_of_birth', 'DATE'),
        ('id_number', 'VARCHAR(50)'),
        ('kyc_document_path', 'VARCHAR(255)'),
        ('id_photo_path', 'VARCHAR(255)'),
        ('id_photo_back_path', 'VARCHAR(255)'),
        ('kyc_status', "VARCHAR(20) DEFAULT 'not_submitted'"),
        ('kyc_submitted_at', 'DATETIME'),
    ]
    with db.session.begin():
        for column_name, column_definition in user_columns:
            if not _table_has_column('users', column_name):
                db.session.execute(text(f'ALTER TABLE users ADD COLUMN {column_name} {column_definition}'))


def ensure_payment_schema():
    """Add payment-related columns to existing tables (SQLite path).

    Legacy databases created before ``external_ref_id`` existed need the column
    added via ALTER TABLE; the index is created with IF NOT EXISTS so startup
    stays idempotent.
    """
    if db.engine is None:
        return
    if db.engine.name != 'sqlite':
        return
    with db.session.begin():
        if not _table_has_column('transactions', 'external_ref_id'):
            db.session.execute(text('ALTER TABLE transactions ADD COLUMN external_ref_id VARCHAR(64)'))
        if not _table_has_column('transactions', 'status'):
            db.session.execute(text("ALTER TABLE transactions ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS idx_transactions_external_ref_id '
            'ON transactions (external_ref_id)'
        ))


def init_db(app):
    """Initialize database with Flask app"""
    # SQLite configuration (will switch to MySQL later)
    app.config['SQLALCHEMY_DATABASE_URI'] ='sqlite:///dealuxe_game.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False  # Set to True for SQL debugging
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        ensure_tournament_schema()
        ensure_user_account_schema()
        ensure_payment_schema()
        print("[DATABASE] Database initialized successfully")


# ========================================
# USER MODEL
# ========================================

class User(db.Model):
    """User authentication and profile"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    full_name = db.Column(db.String(100))
    country = db.Column(db.String(50))
    address = db.Column(db.String(200))
    date_of_birth = db.Column(db.Date)
    id_number = db.Column(db.String(50))

    # KYC / identity verification
    kyc_document_path = db.Column(db.String(255))       # proof of address / KYC doc
    id_photo_path = db.Column(db.String(255))           # ID / passport photo (front)
    id_photo_back_path = db.Column(db.String(255))      # ID / passport photo (back)
    kyc_status = db.Column(db.String(20), default='not_submitted')  # not_submitted/pending_review/verified/rejected
    kyc_submitted_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)  # CLI-bootstrap-only role (promotes/demotes admins)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    player = db.relationship('Player', backref='user', uselist=False, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.now()
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>'


# ========================================
# PLAYER MODEL (Wallet & Stats)
# ========================================

class Player(db.Model):
    """Player wallet and game statistics"""
    __tablename__ = 'players'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Wallet balances
    real_balance = db.Column(db.Float, default=0.0)
    fake_balance = db.Column(db.Float, default=0.0)
    fake_balance_expires_at = db.Column(db.DateTime)
    fake_cash_target = db.Column(db.Float, default=0.0)
    
    # Statistics
    total_games = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    total_wagered = db.Column(db.Float, default=0.0)
    total_winnings = db.Column(db.Float, default=0.0)

    # Daily spending limit (E50 / 24h) — regulatory requirement
    daily_spending_limit = db.Column(db.Float, default=50.0)
    daily_spending_amount = db.Column(db.Float, default=0.0)
    last_spending_reset = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - specify foreign_keys to avoid ambiguity
    bet_sessions = db.relationship('BetSession', 
                                   foreign_keys='BetSession.player_id',
                                   backref='player',
                                   lazy='dynamic')
    
    # Multiplayer rooms as player 1
    rooms_as_player1 = db.relationship('GameRoom',
                                       primaryjoin='Player.user_id==GameRoom.player1_id',
                                       foreign_keys='GameRoom.player1_id',
                                       backref='player1_user',
                                       lazy='dynamic')
    
# Multiplayer rooms as player 2
    rooms_as_player2 = db.relationship('GameRoom',
                                       primaryjoin='Player.user_id==GameRoom.player2_id',
                                       foreign_keys='GameRoom.player2_id',
                                       backref='player2_user',
                                       lazy='dynamic')
    
    def has_sufficient_balance(self, amount, bet_type):
        """Check if player has enough balance for a bet"""
        from config import GameConfig
        if bet_type == GameConfig.BET_TYPE_REAL:
            return self.real_balance >= amount
        elif bet_type == GameConfig.BET_TYPE_FAKE:
            if not self.is_fake_cash_valid():
                return False
            return self.fake_balance >= amount
        return False
    
    def is_fake_cash_valid(self):
        """Check if fake cash hasn't expired"""
        if self.fake_balance_expires_at is None:
            return False
        return datetime.utcnow() < self.fake_balance_expires_at
    
    def award_free_cash(self):
        """Award free cash for 24 hours"""
        from config import GameConfig
        self.fake_balance = GameConfig.get_random_free_cash()
        self.fake_cash_target = GameConfig.get_random_free_target()
        self.fake_balance_expires_at = datetime.utcnow() + GameConfig.get_free_cash_expiry()
        db.session.commit()

    def _rollover_daily_spending(self):
        """Reset the daily spending accumulator if the 24-hour window has elapsed."""
        if self.last_spending_reset:
            time_since_reset = datetime.utcnow() - self.last_spending_reset
            if time_since_reset.total_seconds() > 86400:  # 24 hours
                self.daily_spending_amount = 0.0
                self.last_spending_reset = datetime.utcnow()

    def can_spend(self, amount):
        """Check whether the player may spend `amount` within the E50/24h daily limit."""
        self._rollover_daily_spending()
        return (self.daily_spending_amount + amount) <= self.daily_spending_limit

    def deduct_spending(self, amount):
        """Record spending against the daily limit (call after the charge succeeds)."""
        self._rollover_daily_spending()
        self.daily_spending_amount += amount
        self.last_spending_reset = self.last_spending_reset or datetime.utcnow()

    def deduct_bet(self, amount, bet_type):
        """Deduct bet amount from appropriate balance"""
        from config import GameConfig
        if not self.has_sufficient_balance(amount, bet_type):
            return False
        
        if bet_type == GameConfig.BET_TYPE_REAL:
            self.real_balance -= amount
        elif bet_type == GameConfig.BET_TYPE_FAKE:
            self.fake_balance -= amount
        
        self.total_wagered += amount
        db.session.commit()
        return True
    
    def award_winnings(self, amount, bet_type):
        """Award winnings to player's balance"""
        from config import GameConfig
        if bet_type == GameConfig.BET_TYPE_REAL:
            self.real_balance += amount
        elif bet_type == GameConfig.BET_TYPE_FAKE:
            self.fake_balance += amount
        
        self.total_winnings += amount
        db.session.commit()
    
    def record_game_result(self, won):
        """Update player statistics after a game"""
        self.total_games += 1
        if won:
            self.wins += 1
        else:
            self.losses += 1
        db.session.commit()
    
    def get_win_rate(self):
        """Calculate player's win rate percentage"""
        if self.total_games == 0:
            return 0.0
        return (self.wins / self.total_games) * 100
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'real_balance': self.real_balance,
            'fake_balance': self.fake_balance,
            'fake_balance_expires_at': self.fake_balance_expires_at.isoformat() if self.fake_balance_expires_at else None,
            'fake_cash_target': self.fake_cash_target,
            'is_fake_cash_valid': self.is_fake_cash_valid(),
            'total_games': self.total_games,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': self.get_win_rate(),
            'total_wagered': self.total_wagered,
            'total_winnings': self.total_winnings
        }
    
    def __repr__(self):
        return f'<Player {self.id} - User: {self.user_id}>'
    
    def username(self):
        return self.user.username if self.user else None


# ========================================
# BET SESSION MODEL
# ========================================

class BetSession(db.Model):
    """Tracks betting context for each game session"""
    __tablename__ = 'bet_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(50), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    opponent_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    
    # Game settings
    opponent_type = db.Column(db.String(20), nullable=False)  # 'ai' or 'human'
    bet_type = db.Column(db.String(20), nullable=False)  # 'real' or 'fake'
    bet_amount = db.Column(db.Float, nullable=False)
    prize_pool = db.Column(db.Float, nullable=False)
    card_count = db.Column(db.Integer, default=6)
    
    # Session outcome
    winner_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    win_type = db.Column(db.String(50))  # 'dealuxe', 'escape', 'crazy', 'trail'
    status = db.Column(db.String(20), default='active')  # 'active', 'completed', 'cancelled'

    # Tournament linkage
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    def complete_session(self, winner_id, win_type=None):
        """Mark session as completed with winner"""
        self.winner_id = winner_id
        self.win_type = win_type
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def cancel_session(self):
        """Mark session as cancelled"""
        self.status = 'cancelled'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def is_active(self):
        """Check if session is still active"""
        return self.status == 'active'
    
    def get_duration_seconds(self):
        """Get session duration in seconds"""
        if self.completed_at is None:
            return None
        duration = self.completed_at - self.created_at
        return duration.total_seconds()
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'opponent_id': self.opponent_id,
            'opponent_type': self.opponent_type,
            'bet_type': self.bet_type,
            'bet_amount': self.bet_amount,
            'prize_pool': self.prize_pool,
            'card_count': self.card_count,
            'winner_id': self.winner_id,
            'win_type': self.win_type,
            'status': self.status,
            'tournament_id': self.tournament_id,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.get_duration_seconds(),
            'created_by_username': self.player.user.username if self.player and self.player.user else None
        }
    
    def __repr__(self):
        return f'<BetSession {self.id} - Game: {self.game_id}>'


# ========================================
# GAME HISTORY MODEL
# ========================================

class GameHistory(db.Model):
    """Detailed game history for analytics and replay"""
    __tablename__ = 'game_history'
    
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(50), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('bet_sessions.id'), nullable=True)
    
    # Game details
    player1_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    mode = db.Column(db.String(50))  # 'human_vs_ai', 'human_vs_human'
    
    # Game state snapshot (JSON)
    initial_state = db.Column(db.Text)  # JSON of starting hands
    final_state = db.Column(db.Text)    # JSON of ending state
    move_history = db.Column(db.Text)   # JSON array of all moves
    
    # Outcome
    winner_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    win_condition = db.Column(db.String(50))
    total_turns = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<GameHistory {self.game_id}>'


# ========================================
# LEADERBOARD VIEW (for queries)
# ========================================

class Leaderboard(db.Model):
    """Virtual table/view for leaderboard queries"""
    __tablename__ = 'leaderboard'
    __table_args__ = {'info': {'is_view': True}}
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    username = db.Column(db.String(80))
    total_games = db.Column(db.Integer)
    wins = db.Column(db.Integer)
    win_rate = db.Column(db.Float)
    total_winnings = db.Column(db.Float)
    
    @staticmethod
    def get_top_players(limit=10):
        """Get top players by win rate"""
        return db.session.query(
            Player.id,
            User.username,
            Player.total_games,
            Player.wins,
            Player.total_winnings,
            (Player.wins * 100.0 / db.func.nullif(Player.total_games, 0)).label('win_rate')
        ).join(User).filter(
            Player.total_games >= 5  # Minimum games to qualify
        ).order_by(
            db.desc('win_rate')
        ).limit(limit).all()


# ========================================
# TRANSACTION TYPE CONSTANTS
# Aligned with TOURNAMENT_DATABASE_SCHEMA.md `transaction_log.transaction_type` enum.
# ========================================
TX_ENTRY_FEE = 'entry_fee'        # Player paid to join a tournament (debit)
TX_PRIZE_AWARD = 'prize_award'    # Tournament prize credited to the wallet
TX_REFUND = 'refund'              # Tournament entry refunded
TX_WITHDRAWAL = 'withdrawal'      # Wallet withdrawal / payout
TX_WALLET_TOPUP = 'wallet_topup'  # Player loaded funds into the wallet
TX_BET = 'bet'                    # Versus stake (v1 practice)
TX_WIN = 'win'                    # Versus winnings (v1 practice)
TX_FREE_CASH = 'free_cash'        # Welcome / promotional free cash


# ========================================
# TRANSACTION LOG (for audit trail)
# ========================================

class Transaction(db.Model):
    """Log all wallet transactions for audit"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    external_ref_id = db.Column(db.String(64), nullable=True, index=True)  # strong UUID ref sent to the gateway
    status = db.Column(db.String(20), default='pending')  # pending/completed/failed
    
    transaction_type = db.Column(db.String(50), nullable=False)  # see TX_* constants above
    amount = db.Column(db.Float, nullable=False)
    balance_type = db.Column(db.String(20), nullable=False)  # 'real' or 'fake'
    
    # Balance before and after
    balance_before = db.Column(db.Float)
    balance_after = db.Column(db.Float)
    
    # Related game/session
    session_id = db.Column(db.Integer, db.ForeignKey('bet_sessions.id'))
    game_id = db.Column(db.String(50))
    
    description = db.Column(db.String(255))
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.id} - {self.transaction_type}: {self.amount}>'


class Tournament(db.Model):
    """Represents a tournament instance for the upgraded platform."""
    __tablename__ = 'tournaments'
    __table_args__ = (
        db.CheckConstraint('entry_fee >= 0', name='ck_tournaments_entry_fee_nonnegative'),
        db.CheckConstraint('max_players IN (4, 8, 16)', name='ck_tournaments_max_players_allowed'),
        db.Index('idx_tournaments_status', 'status'),
        db.Index('idx_tournaments_tournament_type', 'tournament_type'),
        db.Index('idx_tournaments_creator_id', 'creator_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tournament_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    tournament_name = db.Column(db.String(255), nullable=False)
    tournament_type = db.Column(db.String(20), nullable=False)  # standard, premium, deluxe
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    entry_fee = db.Column(db.Float, nullable=False, default=10.0)
    prize_pool_amount = db.Column(db.Float, nullable=False, default=0.0)
    max_players = db.Column(db.Integer, nullable=False)
    current_player_count = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default='open')
    is_auto_lock = db.Column(db.Boolean, default=False)
    locked_player_count = db.Column(db.Integer, nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    finals_match_id = db.Column(db.Integer, nullable=True)
    third_place_match_id = db.Column(db.Integer, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    runner_up_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    third_place_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    creator = db.relationship('User', foreign_keys='Tournament.creator_id', backref='created_tournaments')
    bet_sessions = db.relationship('BetSession', foreign_keys='BetSession.tournament_id', backref='tournament', lazy='dynamic')
    game_rooms = db.relationship('GameRoom', foreign_keys='GameRoom.tournament_id', backref='tournament', lazy='dynamic')
    transactions = db.relationship('Transaction', foreign_keys='Transaction.tournament_id', backref='tournament', lazy='dynamic')
    schedule = db.relationship('TournamentSchedule', backref='tournament', uselist=False, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'tournament_code': self.tournament_code,
            'tournament_name': self.tournament_name,
            'tournament_type': self.tournament_type,
            'creator_id': self.creator_id,
            'entry_fee': self.entry_fee,
            'prize_pool_amount': self.prize_pool_amount,
            'max_players': self.max_players,
            'current_player_count': self.current_player_count,
            'status': self.status,
            'is_auto_lock': self.is_auto_lock,
            'locked_player_count': self.locked_player_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class TournamentParticipant(db.Model):
    """Tracks a user's participation in a tournament."""
    __tablename__ = 'tournament_participants'
    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'user_id', name='uq_tournament_participant_tournament_user'),
        db.Index('idx_tournament_participants_tournament_id', 'tournament_id'),
        db.Index('idx_tournament_participants_user_id', 'user_id'),
        db.Index('idx_tournament_participants_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='registered')
    payment_status = db.Column(db.String(20), nullable=False, default='pending')
    transaction_id = db.Column(db.String(255), nullable=True)
    external_payment_id = db.Column(db.String(255), nullable=True)
    paid_amount = db.Column(db.Float, nullable=True)
    payment_method = db.Column(db.String(100), nullable=True)
    final_placement = db.Column(db.Integer, nullable=True)
    prize_awarded = db.Column(db.Float, nullable=False, default=0.0)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    payment_completed_at = db.Column(db.DateTime, nullable=True)
    lock_voted = db.Column(db.Boolean, default=False)  # manual-lock consensus vote (D3)
    withdrew_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    tournament = db.relationship('Tournament', backref='participants')
    user = db.relationship('User', backref='tournament_participations')


class TournamentBracket(db.Model):
    """Represents a bracket slot in a tournament."""
    __tablename__ = 'tournament_brackets'
    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'round_number', 'match_number', name='uq_tournament_bracket_position'),
        db.Index('idx_tournament_brackets_tournament_id', 'tournament_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    round_name = db.Column(db.String(50), nullable=False)
    match_number = db.Column(db.Integer, nullable=False)
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    match_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


class TournamentMatch(db.Model):
    """Represents an individual tournament match bound to a real game room."""
    __tablename__ = 'tournament_matches'
    __table_args__ = (
        db.CheckConstraint('card_count > 0', name='ck_tournament_matches_card_count_positive'),
        db.Index('idx_tournament_matches_tournament_id', 'tournament_id'),
        db.Index('idx_tournament_matches_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    bracket_id = db.Column(db.Integer, nullable=False)
    game_room_id = db.Column(db.Integer, nullable=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='scheduled')
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    loser_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    card_count = db.Column(db.Integer, nullable=False, default=6)
    bet_amount = db.Column(db.Float, nullable=False, default=0.0)
    scheduled_for = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    win_type = db.Column(db.String(50), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    player1_timeout = db.Column(db.Boolean, default=False)
    player2_timeout = db.Column(db.Boolean, default=False)
    player1_forfeited = db.Column(db.Boolean, default=False)
    player2_forfeited = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)


class TournamentPrizePool(db.Model):
    """Tracks prize distribution for a tournament (one row per placement)."""
    __tablename__ = 'tournament_prize_pools'
    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'placement', name='uq_tournament_prize_pool_tournament_placement'),
        db.Index('idx_tournament_prize_pools_tournament_id', 'tournament_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    placement = db.Column(db.Integer, nullable=False)  # 1 = 1st, 2 = 2nd, 3 = 3rd
    prize_percentage = db.Column(db.Float, nullable=False, default=0.0)  # 50.00 / 12.50 / 6.00
    prize_amount = db.Column(db.Float, nullable=False, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    status = db.Column(db.String(20), nullable=False, default='pending')  # pending/awarded/withdrawn/failed

    award_date = db.Column(db.DateTime, nullable=True)
    withdrawal_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WithdrawalRequest(db.Model):
    """Tracks withdrawal requests for tournament prizes."""
    __tablename__ = 'withdrawal_requests'
    __table_args__ = (
        db.Index('idx_withdrawal_requests_user_id', 'user_id'),
        db.Index('idx_withdrawal_requests_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default='pending')
    mobile_number = db.Column(db.String(30), nullable=True)
    transaction_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ========================================
# ADMIN PLATFORM MODELS
# (audit logs, disputes, wallet adjustments — ADMIN_FEATURE_PLAN.md)
# ========================================


class AdminAuditLog(db.Model):
    """Immutable audit trail for every admin action."""
    __tablename__ = 'admin_audit_logs'
    __table_args__ = (
        db.Index('idx_admin_audit_logs_admin_user_id', 'admin_user_id'),
        db.Index('idx_admin_audit_logs_entity', 'entity_type', 'entity_id'),
        db.Index('idx_admin_audit_logs_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AdminAuditLog {self.action} by admin {self.admin_user_id}>'


class Dispute(db.Model):
    """Player dispute filed for payment, result, account or other issues."""
    __tablename__ = 'disputes'
    __table_args__ = (
        db.Index('idx_disputes_user_id', 'user_id'),
        db.Index('idx_disputes_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=True)
    match_id = db.Column(db.Integer, nullable=True)
    category = db.Column(db.String(50), nullable=False)  # payment, result, account, other
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending/in_review/resolved/rejected
    resolution = db.Column(db.Text, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Dispute {self.id} - {self.status}>'


class WalletAdjustment(db.Model):
    """Admin-triggered wallet balance change (with reason + acting admin)."""
    __tablename__ = 'wallet_adjustments'
    __table_args__ = (
        db.Index('idx_wallet_adjustments_user_id', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    balance_type = db.Column(db.String(20), nullable=False)  # real, fake
    delta = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<WalletAdjustment {self.delta:+.2f} {self.balance_type} for user {self.user_id}>'


class TournamentSchedule(db.Model):
    """When a tournament should start (seats filled / in 5-10-20 min / custom time).

    One row per tournament (1:1). `fallback_option` is what happens if the
    scheduled time passes before all seats are filled — default 'seats_filled'.
    """
    __tablename__ = 'tournament_schedules'
    __table_args__ = (
        db.UniqueConstraint('tournament_id', name='uq_tournament_schedules_tournament_id'),
        db.Index('idx_tournament_schedules_scheduled_start_at', 'scheduled_start_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    # seats_filled | in_5min | in_10min | in_20min | custom
    start_option = db.Column(db.String(30), nullable=False, default='seats_filled')
    scheduled_start_at = db.Column(db.DateTime, nullable=True)
    custom_time_str = db.Column(db.String(5), nullable=True)  # 'HH:MM' for display
    fallback_option = db.Column(db.String(30), nullable=False, default='seats_filled')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<TournamentSchedule {self.tournament_id} - {self.start_option}>'


class MatchRoll(db.Model):
    """No-show 'roll game' resolution for a tournament match (10-minute countdown).

    A waiting player rolls the match; if the opponent does not join before the
    deadline, the waiting player wins by no-show and the absent player loses
    their entry stake.
    """
    __tablename__ = 'match_rolls'
    __table_args__ = (
        db.UniqueConstraint('match_id', name='uq_match_rolls_match_id'),
        db.Index('idx_match_rolls_status_deadline', 'status', 'deadline'),
    )

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('tournament_matches.id'), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='rolling')  # rolling/resolved/cancelled
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<MatchRoll {self.match_id} - {self.status}>'


# ========================================
# HELPER FUNCTIONS
# ========================================

def create_user(username, email, password, phone=None, full_name=None, country=None):
    """Create a new user and associated player"""
    user = User(
        username=username,
        email=email,
        phone=phone,
        full_name=full_name,
        country=country,
    )
    user.set_password(password)
    
    db.session.add(user)
    db.session.flush()  # Get user.id before creating player
    
    player = Player(user_id=user.id)
    db.session.add(player)
    
    db.session.commit()
    return user, player


def get_user_by_username(username):
    """Get user by username"""
    return User.query.filter_by(username=username).first()


def get_user_by_email(email):
    """Get user by email"""
    return User.query.filter_by(email=email).first()


def get_player_by_user_id(user_id):
    """Get player profile by user ID"""
    return Player.query.filter_by(user_id=user_id).first()


def create_bet_session(game_id, player_id, opponent_type, bet_type, bet_amount, card_count=6, opponent_id=None, tournament_id=None):
    """Create a new bet session"""
    session = BetSession(
        game_id=game_id,
        player_id=player_id,
        opponent_id=opponent_id,
        opponent_type=opponent_type,
        bet_type=bet_type,
        bet_amount=bet_amount,
        prize_pool=bet_amount * 2,
        card_count=card_count,
        tournament_id=tournament_id,
    )
    db.session.add(session)
    db.session.commit()
    return session


def log_transaction(player_id, transaction_type, amount, balance_type, balance_before, balance_after, 
                    session_id=None, game_id=None, description=None, tournament_id=None):
    """Log a wallet transaction"""
    transaction = Transaction(
        player_id=player_id,
        transaction_type=transaction_type,
        amount=amount,
        balance_type=balance_type,
        balance_before=balance_before,
        balance_after=balance_after,
        session_id=session_id,
        game_id=game_id,
        description=description,
        tournament_id=tournament_id,
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction


def create_tournament_record(creator_id, tournament_type, tournament_name=None, entry_fee=10.0, max_players=None, is_auto_lock=False, locked_player_count=None):
    """Create a basic tournament record and return it."""
    if max_players is None:
        max_players = {'standard': 4, 'premium': 8, 'deluxe': 16}.get(tournament_type, 4)

    code = f"TMT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{tournament_type[:3].upper()}"
    tournament = Tournament(
        tournament_code=code,
        tournament_name=tournament_name or f"{tournament_type.title()} Tournament",
        tournament_type=tournament_type,
        creator_id=creator_id,
        entry_fee=entry_fee,
        prize_pool_amount=entry_fee,
        max_players=max_players,
        current_player_count=1,
        status='open',
        is_auto_lock=is_auto_lock,
        locked_player_count=locked_player_count,
    )
    db.session.add(tournament)
    db.session.flush()
    return tournament


def add_tournament_participant(tournament_id, user_id, payment_status='pending', paid_amount=None, payment_method=None):
    """Register a user into a tournament."""
    participant = TournamentParticipant(
        tournament_id=tournament_id,
        user_id=user_id,
        payment_status=payment_status,
        paid_amount=paid_amount,
        payment_method=payment_method,
    )
    db.session.add(participant)
    db.session.flush()
    return participant


# ========================================
# GAME ROOM MODEL (Multiplayer)
# ========================================

class GameRoom(db.Model):
    """Multiplayer game room for live player vs player games"""
    __tablename__ = 'game_rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    
    # Players
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Game settings
    game_id = db.Column(db.String(100), unique=True, nullable=True)  # UUID from GameManager
    bet_session_id = db.Column(db.Integer, db.ForeignKey('bet_sessions.id'), nullable=True)
    card_count = db.Column(db.Integer, default=6)
    bet_amount = db.Column(db.Float, default=0.0)
    bet_type = db.Column(db.String(10), default='fake')  # 'real' or 'fake'
    
    # Room state
    status = db.Column(db.String(20), default='waiting')  # waiting, in_progress, paused, completed, abandoned
    current_turn_player = db.Column(db.Integer, nullable=True)  # user_id whose turn it is
    turn_deadline = db.Column(db.DateTime, nullable=True)  # when current turn expires
    turn_duration_seconds = db.Column(db.Integer, default=300)  # time limit per turn (5 minutes)
    
    # Pause/Resume
    pause_requested_by = db.Column(db.Integer, nullable=True)  # user_id who requested pause
    pause_approved_by = db.Column(db.Integer, nullable=True)  # user_id who approved pause
    paused_at = db.Column(db.DateTime, nullable=True)
    
    # Reconnection tracking
    player1_connected = db.Column(db.Boolean, default=False)
    player2_connected = db.Column(db.Boolean, default=False)
    player1_last_seen = db.Column(db.DateTime, nullable=True)
    player2_last_seen = db.Column(db.DateTime, nullable=True)
    
    # Results
    winner_id = db.Column(db.Integer, nullable=True)

    # Tournament linkage
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=True)
    match_id = db.Column(db.Integer, db.ForeignKey('tournament_matches.id'), nullable=True)
    is_tournament_game = db.Column(db.Boolean, default=False)  # schema doc marker (G1)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    bet_session = db.relationship('BetSession', backref='game_room', uselist=False)
    
    def to_dict(self):
        """Convert room to dictionary"""
        from datetime import timedelta
        player1_username = User.query.get(self.player1_id).username if self.player1_id else None
        
        # Check if creator is online (connected in last 2 minutes)
        creator_online = False
        if self.player1_last_seen:
            time_since_seen = datetime.utcnow() - self.player1_last_seen
            creator_online = time_since_seen.total_seconds() < 120  # 2 minutes
        
        # Calculate room age and if it's expired (5 hours)
        room_age_hours = (datetime.utcnow() - self.created_at).total_seconds() / 3600
        is_expired = room_age_hours > 5.0
        
        return {
            'id': self.id,
            'room_code': self.room_code,
            'player1_id': self.player1_id,
            'player2_id': self.player2_id,
            'player1_username': player1_username,
            'player2_username': User.query.get(self.player2_id).username if self.player2_id else None,
            'created_by_username': player1_username,  # player1 is always the creator
            'creator_online': creator_online,
            'status': self.status,
            'card_count': self.card_count,
            'bet_amount': self.bet_amount,
            'bet_type': self.bet_type,
            'current_turn_player': self.current_turn_player,
            'turn_deadline': self.turn_deadline.isoformat() if self.turn_deadline else None,
            'turn_duration_seconds': self.turn_duration_seconds,
            'tournament_id': self.tournament_id,
            'match_id': self.match_id,
            'is_tournament_game': self.is_tournament_game,
            'is_paused': self.status == 'paused',
            'pause_requested_by': self.pause_requested_by,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'room_age_hours': round(room_age_hours, 1),
            'is_expired': is_expired,
        }
    
    def can_join(self, user_id):
        """Check if user can join this room"""
        if self.status != 'waiting':
            return False
        if self.player2_id is not None:
            return False
        if self.player1_id == user_id:
            return False
        return True
    
    def is_player_in_room(self, user_id):
        """Check if user is a player in this room"""
        return user_id in [self.player1_id, self.player2_id]
    
    def get_opponent_id(self, user_id):
        """Get opponent's user ID"""
        if user_id == self.player1_id:
            return self.player2_id
        elif user_id == self.player2_id:
            return self.player1_id
        return None
    
    def __repr__(self):
        return f'<GameRoom {self.room_code} - {self.status}>'


# ========================================
# GAME SESSION, MOVES, SNAPSHOTS (Migration additions)
# ========================================


class GameSession(db.Model):
    """Optional consolidated session record for match persistence and reconnection"""
    __tablename__ = 'game_sessions'

    id = db.Column(db.Integer, primary_key=True)
    session_uuid = db.Column(db.String(100), unique=True, nullable=False, index=True)
    game_id = db.Column(db.String(100), nullable=True, index=True)
    game_version = db.Column(db.String(50), nullable=True)

    # JSON/text fields to store players metadata, result and stats
    players = db.Column(db.Text)  # JSON: [{player_id, seat_id, reconnect_token, joined_at, connected}]
    result = db.Column(db.Text)   # JSON: {winner_id, scores}
    stats = db.Column(db.Text)    # JSON: aggregates

    # State tracking
    turn_index = db.Column(db.Integer, default=0)
    phase = db.Column(db.String(50))
    current_turn_player = db.Column(db.Integer, nullable=True)

    status = db.Column(db.String(20), default='waiting')  # waiting, in_progress, completed, abandoned

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    last_active_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<GameSession {self.session_uuid} - {self.status}>'


class Move(db.Model):
    """Persistent move log for every action taken during a match"""
    __tablename__ = 'moves'

    id = db.Column(db.Integer, primary_key=True)
    # Link to either BetSession (existing) or GameSession (new)
    bet_session_id = db.Column(db.Integer, db.ForeignKey('bet_sessions.id'), nullable=True, index=True)
    game_session_id = db.Column(db.Integer, db.ForeignKey('game_sessions.id'), nullable=True, index=True)

    seq_num = db.Column(db.Integer, nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)

    action_type = db.Column(db.String(50), nullable=False)
    action_payload = db.Column(db.Text)   # JSON payload
    result_snapshot = db.Column(db.Text)  # Optional JSON snapshot after move

    idempotency_key = db.Column(db.String(100), index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Move {self.id} - seq:{self.seq_num} type:{self.action_type}>'


class Snapshot(db.Model):
    """Periodic snapshots of the game engine state to speed up restore"""
    __tablename__ = 'snapshots'

    id = db.Column(db.Integer, primary_key=True)
    game_session_id = db.Column(db.Integer, db.ForeignKey('game_sessions.id'), nullable=False, index=True)
    seq_num = db.Column(db.Integer, nullable=False, index=True)
    snapshot_blob = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Snapshot {self.id} - seq:{self.seq_num}>'
