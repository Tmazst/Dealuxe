-- Add tournament linkage columns to existing tables
ALTER TABLE bet_sessions ADD COLUMN tournament_id INTEGER;
ALTER TABLE game_rooms ADD COLUMN tournament_id INTEGER;
ALTER TABLE game_rooms ADD COLUMN match_id INTEGER;
ALTER TABLE transactions ADD COLUMN tournament_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_bet_sessions_tournament_id ON bet_sessions (tournament_id);
CREATE INDEX IF NOT EXISTS idx_game_rooms_tournament_id ON game_rooms (tournament_id);
CREATE INDEX IF NOT EXISTS idx_game_rooms_match_id ON game_rooms (match_id);
CREATE INDEX IF NOT EXISTS idx_transactions_tournament_id ON transactions (tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournaments_status ON tournaments (status);
CREATE INDEX IF NOT EXISTS idx_tournaments_tournament_type ON tournaments (tournament_type);
CREATE INDEX IF NOT EXISTS idx_tournament_participants_tournament_id ON tournament_participants (tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_participants_user_id ON tournament_participants (user_id);
CREATE INDEX IF NOT EXISTS idx_tournament_participants_status ON tournament_participants (status);
CREATE INDEX IF NOT EXISTS idx_tournament_brackets_tournament_id ON tournament_brackets (tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_tournament_id ON tournament_matches (tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_status ON tournament_matches (status);
CREATE INDEX IF NOT EXISTS idx_tournament_prize_pools_tournament_id ON tournament_prize_pools (tournament_id);
CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_user_id ON withdrawal_requests (user_id);
CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_status ON withdrawal_requests (status);
