"""
Player Model
Manages player data, wallet, and game statistics
"""
from datetime import datetime, timedelta
from typing import Optional
from config import GameConfig


class Player:
    """Represents a game player with wallet and statistics"""
    
    def __init__(self, player_id: int, name: str, email: str, phone: str):
        self.id = player_id
        self.name = name
        self.email = email
        self.phone = phone
        
        # Wallet balances
        self.real_balance = 0.0
        self.fake_balance = 0.0
        self.fake_balance_expires_at: Optional[datetime] = None
        self.fake_cash_target = 0.0
        
        # Statistics
        self.total_games = 0
        self.wins = 0
        self.losses = 0
        self.created_at = datetime.now()
    
    def has_sufficient_balance(self, amount: float, bet_type: str) -> bool:
        """Check if player has enough balance for a bet"""
        if bet_type == GameConfig.BET_TYPE_REAL:
            return self.real_balance >= amount
        elif bet_type == GameConfig.BET_TYPE_FAKE:
            # Check if fake cash is still valid
            if not self.is_fake_cash_valid():
                return False
            return self.fake_balance >= amount
        return False
    
    def is_fake_cash_valid(self) -> bool:
        """Check if fake cash hasn't expired"""
        if self.fake_balance_expires_at is None:
            return False
        return datetime.now() < self.fake_balance_expires_at
    
    def award_free_cash(self):
        """Award free cash for 24 hours with random amounts"""
        self.fake_balance = GameConfig.get_random_free_cash()
        self.fake_cash_target = GameConfig.get_random_free_target()
        self.fake_balance_expires_at = datetime.now() + GameConfig.get_free_cash_expiry()
    
    def deduct_bet(self, amount: float, bet_type: str) -> bool:
        """Deduct bet amount from appropriate balance"""
        if not self.has_sufficient_balance(amount, bet_type):
            return False
        
        if bet_type == GameConfig.BET_TYPE_REAL:
            self.real_balance -= amount
        elif bet_type == GameConfig.BET_TYPE_FAKE:
            self.fake_balance -= amount
        
        return True
    
    def award_winnings(self, amount: float, bet_type: str):
        """Award winnings to player's balance"""
        if bet_type == GameConfig.BET_TYPE_REAL:
            self.real_balance += amount
        elif bet_type == GameConfig.BET_TYPE_FAKE:
            self.fake_balance += amount
    
    def record_game_result(self, won: bool):
        """Update player statistics after a game"""
        self.total_games += 1
        if won:
            self.wins += 1
        else:
            self.losses += 1
    
    def get_win_rate(self) -> float:
        """Calculate player's win rate percentage"""
        if self.total_games == 0:
            return 0.0
        return (self.wins / self.total_games) * 100
    
    def to_dict(self):
        """Convert player to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'real_balance': self.real_balance,
            'fake_balance': self.fake_balance,
            'fake_balance_expires_at': self.fake_balance_expires_at.isoformat() if self.fake_balance_expires_at else None,
            'fake_cash_target': self.fake_cash_target,
            'is_fake_cash_valid': self.is_fake_cash_valid(),
            'total_games': self.total_games,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': round(self.get_win_rate(), 2)
        }


# In-memory player storage (will be replaced with database later)
_players = {}
_next_player_id = 1


def create_player(name: str, email: str, phone: str) -> Player:
    """Create a new player"""
    global _next_player_id
    player = Player(_next_player_id, name, email, phone)
    _players[_next_player_id] = player
    _next_player_id += 1
    return player


def get_player(player_id: int) -> Optional[Player]:
    """Get player by ID"""
    return _players.get(player_id)


def get_or_create_demo_player() -> Player:
    """Get or create a demo player for testing"""
    # For now, return player 1 or create it
    if 1 in _players:
        return _players[1]
    
    player = create_player("Demo Player", "demo@example.com", "7600000000")
    player.real_balance = 5000.0  # Demo starting balance
    player.award_free_cash()  # Also award free cash
    return player
