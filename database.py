"""
Database Configuration and Models
SQLAlchemy setup for Dealuxe Card Game
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def init_db(app):
    """Initialize database with Flask app"""
    # SQLite configuration (will switch to MySQL later)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dealuxe_game.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False  # Set to True for SQL debugging
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
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
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
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
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - specify foreign_keys to avoid ambiguity
    bet_sessions = db.relationship('BetSession', 
                                   foreign_keys='BetSession.player_id',
                                   backref='player', 
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
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.get_duration_seconds()
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
# TRANSACTION LOG (for audit trail)
# ========================================

class Transaction(db.Model):
    """Log all wallet transactions for audit"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    
    transaction_type = db.Column(db.String(50), nullable=False)  # 'bet', 'win', 'deposit', 'withdrawal', 'free_cash'
    amount = db.Column(db.Float, nullable=False)
    balance_type = db.Column(db.String(20), nullable=False)  # 'real' or 'fake'
    
    # Balance before and after
    balance_before = db.Column(db.Float)
    balance_after = db.Column(db.Float)
    
    # Related game/session
    session_id = db.Column(db.Integer, db.ForeignKey('bet_sessions.id'))
    game_id = db.Column(db.String(50))
    
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.id} - {self.transaction_type}: {self.amount}>'


# ========================================
# HELPER FUNCTIONS
# ========================================

def create_user(username, email, password, phone=None, full_name=None):
    """Create a new user and associated player"""
    user = User(
        username=username,
        email=email,
        phone=phone,
        full_name=full_name
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


def create_bet_session(game_id, player_id, opponent_type, bet_type, bet_amount, card_count=6, opponent_id=None):
    """Create a new bet session"""
    session = BetSession(
        game_id=game_id,
        player_id=player_id,
        opponent_id=opponent_id,
        opponent_type=opponent_type,
        bet_type=bet_type,
        bet_amount=bet_amount,
        prize_pool=bet_amount * 2,
        card_count=card_count
    )
    db.session.add(session)
    db.session.commit()
    return session


def log_transaction(player_id, transaction_type, amount, balance_type, balance_before, balance_after, 
                    session_id=None, game_id=None, description=None):
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
        description=description
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction
