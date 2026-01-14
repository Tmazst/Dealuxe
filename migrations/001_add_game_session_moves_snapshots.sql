-- Migration: Add game_sessions, moves, snapshots tables
-- Generated draft migration for SQLite (adjust for MySQL/Postgres as needed)

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS game_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid VARCHAR(100) NOT NULL UNIQUE,
    game_id VARCHAR(100),
    game_version VARCHAR(50),
    players TEXT,
    result TEXT,
    stats TEXT,
    turn_index INTEGER DEFAULT 0,
    phase VARCHAR(50),
    current_turn_player INTEGER,
    status VARCHAR(20) DEFAULT 'waiting',
    created_at DATETIME DEFAULT (datetime('now')),
    started_at DATETIME,
    ended_at DATETIME,
    last_active_at DATETIME,
    expires_at DATETIME
);

CREATE INDEX IF NOT EXISTS ix_game_sessions_session_uuid ON game_sessions(session_uuid);
CREATE INDEX IF NOT EXISTS ix_game_sessions_game_id ON game_sessions(game_id);

CREATE TABLE IF NOT EXISTS moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_session_id INTEGER,
    game_session_id INTEGER,
    seq_num INTEGER NOT NULL,
    player_id INTEGER,
    action_type VARCHAR(50) NOT NULL,
    action_payload TEXT,
    result_snapshot TEXT,
    idempotency_key VARCHAR(100),
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_moves_bet_session_id ON moves(bet_session_id);
CREATE INDEX IF NOT EXISTS ix_moves_game_session_id ON moves(game_session_id);
CREATE INDEX IF NOT EXISTS ix_moves_seq_num ON moves(seq_num);
CREATE INDEX IF NOT EXISTS ix_moves_idempotency_key ON moves(idempotency_key);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_session_id INTEGER NOT NULL,
    seq_num INTEGER NOT NULL,
    snapshot_blob TEXT NOT NULL,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_snapshots_game_session_id ON snapshots(game_session_id);
CREATE INDEX IF NOT EXISTS ix_snapshots_seq_num ON snapshots(seq_num);

COMMIT;
