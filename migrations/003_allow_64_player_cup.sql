-- One-time SQLite migration for the Version 3 64-player Cup.
-- Ordinary tournaments remain restricted to 4, 8 or 16 seats.
PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TABLE tournaments_v3 (
    id INTEGER NOT NULL PRIMARY KEY,
    tournament_code VARCHAR(20) NOT NULL,
    tournament_name VARCHAR(255) NOT NULL,
    tournament_type VARCHAR(20) NOT NULL,
    creator_id INTEGER NOT NULL,
    entry_fee FLOAT NOT NULL,
    prize_pool_amount FLOAT NOT NULL,
    max_players INTEGER NOT NULL,
    current_player_count INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    is_auto_lock BOOLEAN,
    locked_player_count INTEGER,
    locked_at DATETIME,
    created_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME,
    finals_match_id INTEGER,
    third_place_match_id INTEGER,
    winner_id INTEGER,
    runner_up_id INTEGER,
    third_place_id INTEGER,
    notes TEXT,
    CONSTRAINT ck_tournaments_entry_fee_nonnegative CHECK (entry_fee >= 0),
    CONSTRAINT ck_tournaments_max_players_allowed CHECK (
        (tournament_type = 'cup' AND max_players = 64) OR
        (tournament_type != 'cup' AND max_players IN (4, 8, 16))
    ),
    FOREIGN KEY(creator_id) REFERENCES users (id),
    FOREIGN KEY(winner_id) REFERENCES users (id),
    FOREIGN KEY(runner_up_id) REFERENCES users (id),
    FOREIGN KEY(third_place_id) REFERENCES users (id)
);

INSERT INTO tournaments_v3 (
    id, tournament_code, tournament_name, tournament_type, creator_id,
    entry_fee, prize_pool_amount, max_players, current_player_count, status,
    is_auto_lock, locked_player_count, locked_at, created_at, started_at,
    completed_at, finals_match_id, third_place_match_id, winner_id,
    runner_up_id, third_place_id, notes
)
SELECT
    id, tournament_code, tournament_name, tournament_type, creator_id,
    entry_fee, prize_pool_amount, max_players, current_player_count, status,
    is_auto_lock, locked_player_count, locked_at, created_at, started_at,
    completed_at, finals_match_id, third_place_match_id, winner_id,
    runner_up_id, third_place_id, notes
FROM tournaments;

DROP TABLE tournaments;
ALTER TABLE tournaments_v3 RENAME TO tournaments;

CREATE UNIQUE INDEX ix_tournaments_tournament_code ON tournaments (tournament_code);
CREATE INDEX idx_tournaments_status ON tournaments (status);
CREATE INDEX idx_tournaments_tournament_type ON tournaments (tournament_type);
CREATE INDEX idx_tournaments_creator_id ON tournaments (creator_id);

COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA foreign_key_check;
