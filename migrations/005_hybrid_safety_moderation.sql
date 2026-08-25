-- Version 3 Hybrid safety foundation: moderation history, blocks and reports.
ALTER TABLE discovery_profiles ADD COLUMN moderation_note VARCHAR(500);
ALTER TABLE discovery_profiles ADD COLUMN moderated_by INTEGER REFERENCES users(id);
ALTER TABLE discovery_profiles ADD COLUMN moderated_at DATETIME;

CREATE TABLE IF NOT EXISTS user_blocks (
    id INTEGER NOT NULL PRIMARY KEY,
    blocker_id INTEGER NOT NULL,
    blocked_id INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_user_blocks_pair UNIQUE (blocker_id, blocked_id),
    FOREIGN KEY(blocker_id) REFERENCES users (id),
    FOREIGN KEY(blocked_id) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker_active
    ON user_blocks (blocker_id, is_active);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked_active
    ON user_blocks (blocked_id, is_active);

CREATE TABLE IF NOT EXISTS discovery_reports (
    id INTEGER NOT NULL PRIMARY KEY,
    reporter_id INTEGER NOT NULL,
    reported_user_id INTEGER NOT NULL,
    profile_id INTEGER,
    tournament_id INTEGER,
    match_id INTEGER,
    reason_code VARCHAR(40) NOT NULL,
    details VARCHAR(1000),
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolution VARCHAR(1000),
    reviewed_by INTEGER,
    reviewed_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(reporter_id) REFERENCES users (id),
    FOREIGN KEY(reported_user_id) REFERENCES users (id),
    FOREIGN KEY(profile_id) REFERENCES discovery_profiles (id),
    FOREIGN KEY(tournament_id) REFERENCES tournaments (id),
    FOREIGN KEY(reviewed_by) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_discovery_reports_reporter
    ON discovery_reports (reporter_id);
CREATE INDEX IF NOT EXISTS idx_discovery_reports_reported
    ON discovery_reports (reported_user_id);
CREATE INDEX IF NOT EXISTS idx_discovery_reports_status
    ON discovery_reports (status);
