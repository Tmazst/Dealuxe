"""
Bet Session Model
Tracks betting context for each game session
"""
from datetime import datetime
from typing import Optional
from config import GameConfig


class BetSession:
    """Represents a game session with betting context"""
    
    def __init__(
        self,
        session_id: int,
        game_id: str,
        player_id: int,
        opponent_type: str,
        bet_type: str,
        bet_amount: float,
        card_count: int = 6
    ):
        self.id = session_id
        self.game_id = game_id
        self.player_id = player_id
        self.opponent_type = opponent_type  # 'ai' or 'human'
        self.bet_type = bet_type  # 'real' or 'fake'
        self.bet_amount = bet_amount
        self.card_count = card_count
        
        # Prize pool (player bet + opponent bet)
        self.prize_pool = bet_amount * 2
        
        # Session tracking
        self.winner_id: Optional[int] = None
        self.status = GameConfig.SESSION_ACTIVE
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None
    
    def complete_session(self, winner_id: int):
        """Mark session as completed with winner"""
        self.winner_id = winner_id
        self.status = GameConfig.SESSION_COMPLETED
        self.completed_at = datetime.now()
    
    def cancel_session(self):
        """Mark session as cancelled (e.g., player disconnected)"""
        self.status = GameConfig.SESSION_CANCELLED
        self.completed_at = datetime.now()
    
    def is_active(self) -> bool:
        """Check if session is still active"""
        return self.status == GameConfig.SESSION_ACTIVE
    
    def player_won(self, player_id: int) -> bool:
        """Check if specified player won this session"""
        return self.winner_id == player_id
    
    def get_duration_seconds(self) -> Optional[float]:
        """Get session duration in seconds"""
        if self.completed_at is None:
            return None
        duration = self.completed_at - self.created_at
        return duration.total_seconds()
    
    def to_dict(self):
        """Convert session to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'opponent_type': self.opponent_type,
            'bet_type': self.bet_type,
            'bet_amount': self.bet_amount,
            'prize_pool': self.prize_pool,
            'card_count': self.card_count,
            'winner_id': self.winner_id,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.get_duration_seconds()
        }


# In-memory session storage (will be replaced with database later)
_sessions = {}
_next_session_id = 1
_game_to_session = {}  # Map game_id to session_id


def create_session(
    game_id: str,
    player_id: int,
    opponent_type: str,
    bet_type: str,
    bet_amount: float,
    card_count: int = 6
) -> BetSession:
    """Create a new bet session"""
    global _next_session_id
    
    session = BetSession(
        _next_session_id,
        game_id,
        player_id,
        opponent_type,
        bet_type,
        bet_amount,
        card_count
    )
    
    _sessions[_next_session_id] = session
    _game_to_session[game_id] = _next_session_id
    _next_session_id += 1
    
    return session


def get_session(session_id: int) -> Optional[BetSession]:
    """Get session by ID"""
    return _sessions.get(session_id)


def get_session_by_game(game_id: str) -> Optional[BetSession]:
    """Get session by game ID"""
    session_id = _game_to_session.get(game_id)
    if session_id:
        return _sessions.get(session_id)
    return None


def get_active_sessions(player_id: int) -> list:
    """Get all active sessions for a player"""
    return [
        session for session in _sessions.values()
        if session.player_id == player_id and session.is_active()
    ]


def get_player_session_history(player_id: int, limit: int = 10) -> list:
    """Get player's recent session history"""
    player_sessions = [
        session for session in _sessions.values()
        if session.player_id == player_id
    ]
    # Sort by created_at descending
    player_sessions.sort(key=lambda s: s.created_at, reverse=True)
    return player_sessions[:limit]
