.dbconfig defensive off
BEGIN;
PRAGMA writable_schema = on;
PRAGMA foreign_keys = off;
PRAGMA encoding = 'UTF-8';
PRAGMA page_size = '4096';
PRAGMA auto_vacuum = '0';
PRAGMA user_version = '0';
PRAGMA application_id = '0';
CREATE TABLE lost_and_found(rootpgno INTEGER, pgno INTEGER, nfield INTEGER, id INTEGER, c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, c20, c21);
INSERT INTO lost_and_found VALUES(2, 2, 22, 1, NULL, 'player1', 'player1@test.com', NULL, 'pbkdf2:sha256:600000$SFMrrGs4wWfBfgOi$e75f6e16b1f2cebd0b559f2620d4e80e86207f12f54edf17356b0d2f179814d4', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 14:33:00.965251', '2026-09-01 14:33:02.758521');
INSERT INTO lost_and_found VALUES(2, 2, 22, 2, NULL, 'player2', 'player2@test.com', NULL, 'pbkdf2:sha256:600000$Ar2uvfmtCFNUDvfN$f699b0da78a4e30b3b5c1c00dc5d49a29289c6d3f757db7b79f85c030895dd5b', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 14:33:01.249796', NULL);
INSERT INTO lost_and_found VALUES(2, 2, 22, 3, NULL, 'player3', 'player3@test.com', NULL, 'pbkdf2:sha256:600000$wv47Hna9xKb9XGbc$37961512c7ea366eb8e2b9f5b4c2654a578bbd8fbe3a5cfbe5cb74de090201f4', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 14:33:01.589798', NULL);
INSERT INTO lost_and_found VALUES(2, 2, 22, 4, NULL, 'player4', 'player4@test.com', NULL, 'pbkdf2:sha256:600000$qRrGjG5PmchRikYU$23d3723566b9059340363f576bfd8e88b8a9ecede1d3bf8a804b105d2a0a376a', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 14:33:01.892481', NULL);
INSERT INTO lost_and_found VALUES(3, 3, 2, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(3, 3, 2, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(3, 3, 2, NULL, NULL, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(3, 3, 2, NULL, NULL, 4, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(4, 4, 2, NULL, 'player1@test.com', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(4, 4, 2, NULL, 'player2@test.com', 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(4, 4, 2, NULL, 'player3@test.com', 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(4, 4, 2, NULL, 'player4@test.com', 4, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(5, 5, 2, NULL, 'player1', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(5, 5, 2, NULL, 'player2', 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(5, 5, 2, NULL, 'player3', 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(5, 5, 2, NULL, 'player4', 4, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(11, 11, 16, 1, NULL, 1, 90, 0, NULL, 0, 0, 0, 0, 10, 0, 50, 10, '2026-09-01 12:33:02.354483', '2026-09-01 12:33:01.249796', '2026-09-01 12:33:02.355485', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(11, 11, 16, 2, NULL, 2, 100, 0, NULL, 0, 0, 0, 0, 0, 0, 50, 0, NULL, '2026-09-01 12:33:01.589798', '2026-09-01 12:33:01.589798', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(11, 11, 16, 3, NULL, 3, 100, 0, NULL, 0, 0, 0, 0, 0, 0, 50, 0, NULL, '2026-09-01 12:33:01.892481', '2026-09-01 12:33:01.892481', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(11, 11, 16, 4, NULL, 4, 100, 0, NULL, 0, 0, 0, 0, 0, 0, 50, 0, NULL, '2026-09-01 12:33:01.893483', '2026-09-01 12:33:01.893483', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(12, 12, 2, NULL, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(12, 12, 2, NULL, 2, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(12, 12, 2, NULL, 3, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(12, 12, 2, NULL, 4, 4, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(13, 13, 22, 1, NULL, 'TMT-E37C5276126041B2', 'Sched Cup', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 12:33:02.349482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(14, 14, 2, NULL, 'open', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(15, 15, 2, NULL, 'standard', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 1, 'table', 'users', 'users', 2, 'CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	phone VARCHAR(20), 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(100), 
	country VARCHAR(50), 
	address VARCHAR(200), 
	date_of_birth DATE, 
	id_number VARCHAR(50), 
	kyc_document_path VARCHAR(255), 
	id_photo_path VARCHAR(255), 
	id_photo_back_path VARCHAR(255), 
	profile_image_path VARCHAR(255), 
	kyc_status VARCHAR(20), 
	kyc_submitted_at DATETIME, 
	is_active BOOLEAN, 
	is_admin BOOLEAN, 
	is_super_admin BOOLEAN, 
	verified_referral_count INTEGER NOT NULL, 
	created_at DATETIME, 
	last_login DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (phone)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 2, 'index', 'sqlite_autoindex_users_1', 'users', 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 3, 'index', 'ix_users_email', 'users', 4, 'CREATE UNIQUE INDEX ix_users_email ON users (email)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 4, 'index', 'ix_users_username', 'users', 5, 'CREATE UNIQUE INDEX ix_users_username ON users (username)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 5, 'table', 'hybrid_pilot_metrics', 'hybrid_pilot_metrics', 6, 'CREATE TABLE hybrid_pilot_metrics (
	id INTEGER NOT NULL, 
	metric_key VARCHAR(80) NOT NULL, 
	total_count INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (metric_key)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 6, 'index', 'sqlite_autoindex_hybrid_pilot_metrics_1', 'hybrid_pilot_metrics', 7, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 7, 'table', 'game_sessions', 'game_sessions', 8, 'CREATE TABLE game_sessions (
	id INTEGER NOT NULL, 
	session_uuid VARCHAR(100) NOT NULL, 
	game_id VARCHAR(100), 
	game_version VARCHAR(50), 
	players TEXT, 
	result TEXT, 
	stats TEXT, 
	turn_index INTEGER, 
	phase VARCHAR(50), 
	current_turn_player INTEGER, 
	status VARCHAR(20), 
	created_at DATETIME, 
	started_at DATETIME, 
	ended_at DATETIME, 
	last_active_at DATETIME, 
	expires_at DATETIME, 
	PRIMARY KEY (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 8, 'index', 'ix_game_sessions_game_id', 'game_sessions', 9, 'CREATE INDEX ix_game_sessions_game_id ON game_sessions (game_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 9, 'index', 'ix_game_sessions_session_uuid', 'game_sessions', 10, 'CREATE UNIQUE INDEX ix_game_sessions_session_uuid ON game_sessions (session_uuid)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(16, 16, 5, 10, 'table', 'players', 'players', 11, 'CREATE TABLE players (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	real_balance FLOAT, 
	fake_balance FLOAT, 
	fake_balance_expires_at DATETIME, 
	fake_cash_target FLOAT, 
	total_games INTEGER, 
	wins INTEGER, 
	losses INTEGER, 
	total_wagered FLOAT, 
	total_winnings FLOAT, 
	daily_spending_limit FLOAT, 
	daily_spending_amount FLOAT, 
	last_spending_reset DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(17, 17, 2, NULL, 'TMT-E37C5276126041B2', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(18, 18, 5, 11, 'index', 'sqlite_autoindex_players_1', 'players', 12, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(18, 18, 5, 12, 'table', 'tournaments', 'tournaments', 13, 'CREATE TABLE tournaments (
	id INTEGER NOT NULL, 
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
	PRIMARY KEY (id), 
	CONSTRAINT ck_tournaments_entry_fee_nonnegative CHECK (entry_fee >= 0), 
	CONSTRAINT ck_tournaments_max_players_allowed CHECK ((tournament_type = ''cup'' AND max_players = 64) OR (tournament_type != ''cup'' AND max_players IN (4, 8, 16))), 
	FOREIGN KEY(creator_id) REFERENCES users (id), 
	FOREIGN KEY(winner_id) REFERENCES users (id), 
	FOREIGN KEY(runner_up_id) REFERENCES users (id), 
	FOREIGN KEY(third_place_id) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(18, 18, 5, 13, 'index', 'idx_tournaments_status', 'tournaments', 14, 'CREATE INDEX idx_tournaments_status ON tournaments (status)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(18, 18, 5, 14, 'index', 'idx_tournaments_tournament_type', 'tournaments', 15, 'CREATE INDEX idx_tournaments_tournament_type ON tournaments (tournament_type)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(18, 18, 5, 15, 'index', 'ix_tournaments_tournament_code', 'tournaments', 17, 'CREATE UNIQUE INDEX ix_tournaments_tournament_code ON tournaments (tournament_code)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(18, 18, 5, 16, 'index', 'idx_tournaments_creator_id', 'tournaments', 19, 'CREATE INDEX idx_tournaments_creator_id ON tournaments (creator_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(19, 19, 2, NULL, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 26, 'index', 'sqlite_autoindex_hybrid_feature_settings_1', 'hybrid_feature_settings', 29, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 27, 'index', 'idx_hybrid_feature_settings_updated', 'hybrid_feature_settings', 30, 'CREATE INDEX idx_hybrid_feature_settings_updated ON hybrid_feature_settings (updated_at)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 28, 'table', 'discovery_caption_templates', 'discovery_caption_templates', 31, 'CREATE TABLE discovery_caption_templates (
	id INTEGER NOT NULL, 
	code VARCHAR(80) NOT NULL, 
	display_name VARCHAR(120) NOT NULL, 
	intent VARCHAR(30) NOT NULL, 
	category VARCHAR(50), 
	template_text VARCHAR(280) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 29, 'index', 'sqlite_autoindex_discovery_caption_templates_1', 'discovery_caption_templates', 32, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 30, 'index', 'idx_discovery_caption_templates_active', 'discovery_caption_templates', 33, 'CREATE INDEX idx_discovery_caption_templates_active ON discovery_caption_templates (is_active)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 31, 'index', 'idx_discovery_caption_templates_intent_category', 'discovery_caption_templates', 34, 'CREATE INDEX idx_discovery_caption_templates_intent_category ON discovery_caption_templates (intent, category)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 32, 'table', 'admin_audit_logs', 'admin_audit_logs', 35, 'CREATE TABLE admin_audit_logs (
	id INTEGER NOT NULL, 
	admin_user_id INTEGER NOT NULL, 
	action VARCHAR(100) NOT NULL, 
	entity_type VARCHAR(50), 
	entity_id INTEGER, 
	summary VARCHAR(255), 
	details TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(admin_user_id) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 33, 'index', 'idx_admin_audit_logs_created_at', 'admin_audit_logs', 37, 'CREATE INDEX idx_admin_audit_logs_created_at ON admin_audit_logs (created_at)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 34, 'index', 'idx_admin_audit_logs_admin_user_id', 'admin_audit_logs', 38, 'CREATE INDEX idx_admin_audit_logs_admin_user_id ON admin_audit_logs (admin_user_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(36, 36, 5, 35, 'index', 'idx_admin_audit_logs_entity', 'admin_audit_logs', 39, 'CREATE INDEX idx_admin_audit_logs_entity ON admin_audit_logs (entity_type, entity_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(48, 48, 16, 1, NULL, 1, 1, 'registered', 'completed', NULL, NULL, 10, 'wallet', NULL, 0, '2026-09-01 12:33:02.351483', '2026-09-01 12:33:02.368482', 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(49, 49, 3, NULL, 1, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(50, 50, 2, NULL, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(51, 51, 2, NULL, 'registered', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 42, 'index', 'ix_bet_sessions_game_id', 'bet_sessions', 46, 'CREATE INDEX ix_bet_sessions_game_id ON bet_sessions (game_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 43, 'table', 'leaderboard', 'leaderboard', 47, 'CREATE TABLE leaderboard (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	player_id INTEGER, 
	username VARCHAR(80), 
	total_games INTEGER, 
	wins INTEGER, 
	win_rate FLOAT, 
	total_winnings FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(player_id) REFERENCES players (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 44, 'table', 'tournament_participants', 'tournament_participants', 48, 'CREATE TABLE tournament_participants (
	id INTEGER NOT NULL, 
	tournament_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	payment_status VARCHAR(20) NOT NULL, 
	transaction_id VARCHAR(255), 
	external_payment_id VARCHAR(255), 
	paid_amount FLOAT, 
	payment_method VARCHAR(100), 
	final_placement INTEGER, 
	prize_awarded FLOAT NOT NULL, 
	registered_at DATETIME, 
	payment_completed_at DATETIME, 
	lock_voted BOOLEAN, 
	withdrew_at DATETIME, 
	notes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_participant_tournament_user UNIQUE (tournament_id, user_id), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 45, 'index', 'sqlite_autoindex_tournament_participants_1', 'tournament_participants', 49, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 46, 'index', 'idx_tournament_participants_user_id', 'tournament_participants', 50, 'CREATE INDEX idx_tournament_participants_user_id ON tournament_participants (user_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 47, 'index', 'idx_tournament_participants_status', 'tournament_participants', 51, 'CREATE INDEX idx_tournament_participants_status ON tournament_participants (status)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(52, 52, 5, 48, 'index', 'idx_tournament_participants_tournament_id', 'tournament_participants', 53, 'CREATE INDEX idx_tournament_participants_tournament_id ON tournament_participants (tournament_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(53, 53, 2, NULL, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 55, 'index', 'idx_discovery_reports_reporter', 'discovery_reports', 60, 'CREATE INDEX idx_discovery_reports_reporter ON discovery_reports (reporter_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 56, 'index', 'idx_discovery_reports_status', 'discovery_reports', 61, 'CREATE INDEX idx_discovery_reports_status ON discovery_reports (status)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 57, 'index', 'idx_discovery_reports_reported', 'discovery_reports', 62, 'CREATE INDEX idx_discovery_reports_reported ON discovery_reports (reported_user_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 58, 'table', 'discovery_match_audits', 'discovery_match_audits', 63, 'CREATE TABLE discovery_match_audits (
	id INTEGER NOT NULL, 
	tournament_id INTEGER NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	algorithm_version VARCHAR(80) NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	participant_count INTEGER NOT NULL, 
	total_score INTEGER NOT NULL, 
	hybrid_pair_count INTEGER NOT NULL, 
	matching_duration_ms FLOAT, 
	legacy_fallback_recommended BOOLEAN NOT NULL, 
	proposed_seed_order_json TEXT NOT NULL, 
	legacy_seed_order_json TEXT NOT NULL, 
	pairs_json TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_discovery_match_audits_run UNIQUE (tournament_id, mode, algorithm_version), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 59, 'index', 'sqlite_autoindex_discovery_match_audits_1', 'discovery_match_audits', 64, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 60, 'index', 'idx_discovery_match_audits_tournament', 'discovery_match_audits', 65, 'CREATE INDEX idx_discovery_match_audits_tournament ON discovery_match_audits (tournament_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(66, 66, 5, 61, 'index', 'idx_discovery_match_audits_created', 'discovery_match_audits', 67, 'CREATE INDEX idx_discovery_match_audits_created ON discovery_match_audits (created_at)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(74, 74, 11, 1, NULL, 1, 1, 50, 5, NULL, 'pending', NULL, NULL, NULL, '2026-09-01 12:33:02.380482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(74, 74, 11, 2, NULL, 1, 2, 12.5, 1.25, NULL, 'pending', NULL, NULL, NULL, '2026-09-01 12:33:02.380482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(74, 74, 11, 3, NULL, 1, 3, 6, 0.6, NULL, 'pending', NULL, NULL, NULL, '2026-09-01 12:33:02.380482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(75, 75, 3, NULL, 1, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(75, 75, 3, NULL, 1, 2, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(75, 75, 3, NULL, 1, 3, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(76, 76, 2, NULL, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(76, 76, 2, NULL, 1, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(76, 76, 2, NULL, 1, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(80, 80, 5, 68, 'table', 'tournament_prize_pools', 'tournament_prize_pools', 74, 'CREATE TABLE tournament_prize_pools (
	id INTEGER NOT NULL, 
	tournament_id INTEGER NOT NULL, 
	placement INTEGER NOT NULL, 
	prize_percentage FLOAT NOT NULL, 
	prize_amount FLOAT NOT NULL, 
	user_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	award_date DATETIME, 
	withdrawal_date DATETIME, 
	notes TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_prize_pool_tournament_placement UNIQUE (tournament_id, placement), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(80, 80, 5, 69, 'index', 'sqlite_autoindex_tournament_prize_pools_1', 'tournament_prize_pools', 75, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(80, 80, 5, 70, 'index', 'idx_tournament_prize_pools_tournament_id', 'tournament_prize_pools', 76, 'CREATE INDEX idx_tournament_prize_pools_tournament_id ON tournament_prize_pools (tournament_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(80, 80, 5, 71, 'table', 'withdrawal_requests', 'withdrawal_requests', 77, 'CREATE TABLE withdrawal_requests (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	tournament_id INTEGER, 
	amount FLOAT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	mobile_number VARCHAR(30), 
	transaction_id VARCHAR(255), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(80, 80, 5, 72, 'index', 'idx_withdrawal_requests_user_id', 'withdrawal_requests', 78, 'CREATE INDEX idx_withdrawal_requests_user_id ON withdrawal_requests (user_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(80, 80, 5, 73, 'index', 'idx_withdrawal_requests_status', 'withdrawal_requests', 79, 'CREATE INDEX idx_withdrawal_requests_status ON withdrawal_requests (status)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(84, 84, 7, 1, NULL, 1, 'in_5min', '2026-09-01 12:38:02.347483', NULL, 'seats_filled', '2026-09-01 12:33:02.352483', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(85, 85, 2, NULL, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(86, 86, 2, NULL, '2026-09-01 12:38:02.347483', 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(89, 89, 14, 1, NULL, 1, NULL, 'initiated', 'entry_fee', 10, 'real', 100, 90, NULL, NULL, 'Tournament entry #1', 1, '2026-09-01 12:33:02.355485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(90, 90, 2, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 83, 'index', 'ix_transactions_external_ref_id', 'transactions', 90, 'CREATE INDEX ix_transactions_external_ref_id ON transactions (external_ref_id)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 84, 'table', 'match_rolls', 'match_rolls', 91, 'CREATE TABLE match_rolls (
	id INTEGER NOT NULL, 
	match_id INTEGER NOT NULL, 
	requested_by INTEGER NOT NULL, 
	requested_at DATETIME, 
	deadline DATETIME NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	winner_id INTEGER, 
	resolved_at DATETIME, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_match_rolls_match_id UNIQUE (match_id), 
	FOREIGN KEY(match_id) REFERENCES tournament_matches (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id), 
	FOREIGN KEY(winner_id) REFERENCES users (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 85, 'index', 'sqlite_autoindex_match_rolls_1', 'match_rolls', 92, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 86, 'index', 'idx_match_rolls_status_deadline', 'match_rolls', 93, 'CREATE INDEX idx_match_rolls_status_deadline ON match_rolls (status, deadline)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 87, 'table', 'game_rooms', 'game_rooms', 94, 'CREATE TABLE game_rooms (
	id INTEGER NOT NULL, 
	room_code VARCHAR(10) NOT NULL, 
	player1_id INTEGER NOT NULL, 
	player2_id INTEGER, 
	game_id VARCHAR(100), 
	bet_session_id INTEGER, 
	card_count INTEGER, 
	bet_amount FLOAT, 
	bet_type VARCHAR(10), 
	status VARCHAR(20), 
	current_turn_player INTEGER, 
	turn_deadline DATETIME, 
	turn_duration_seconds INTEGER, 
	pause_requested_by INTEGER, 
	pause_approved_by INTEGER, 
	paused_at DATETIME, 
	player1_connected BOOLEAN, 
	player2_connected BOOLEAN, 
	player1_last_seen DATETIME, 
	player2_last_seen DATETIME, 
	player1_profile_visible BOOLEAN NOT NULL, 
	player2_profile_visible BOOLEAN NOT NULL, 
	winner_id INTEGER, 
	tournament_id INTEGER, 
	match_id INTEGER, 
	is_tournament_game BOOLEAN, 
	created_at DATETIME, 
	started_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(player1_id) REFERENCES users (id), 
	FOREIGN KEY(player2_id) REFERENCES users (id), 
	UNIQUE (game_id), 
	FOREIGN KEY(bet_session_id) REFERENCES bet_sessions (id), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id), 
	FOREIGN KEY(match_id) REFERENCES tournament_matches (id)
)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 88, 'index', 'sqlite_autoindex_game_rooms_1', 'game_rooms', 95, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(96, 96, 5, 89, 'index', 'ix_game_rooms_room_code', 'game_rooms', 97, 'CREATE UNIQUE INDEX ix_game_rooms_room_code ON game_rooms (room_code)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 1, NULL, 'TMT-2C2E041A92744980', 'Cup Qualifier 1', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.350488', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 2, NULL, 'TMT-08DD7DC7EA4444C4', 'Cup Qualifier 2', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.351481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 3, NULL, 'TMT-6A32A0533260414A', 'Cup Qualifier 3', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.352487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 4, NULL, 'TMT-7124C434BB224B5B', 'Cup Qualifier 4', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.353487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 5, NULL, 'TMT-22AD47CAF69F4388', 'Cup Qualifier 5', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.354485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 6, NULL, 'TMT-89AB74F1533E45A4', 'Cup Qualifier 6', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.355483', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 7, NULL, 'TMT-DA2FB67B2B5D4ECB', 'Cup Qualifier 7', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.355483', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 8, NULL, 'TMT-3D3A7FA4F4954286', 'Cup Qualifier 8', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.356487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 9, NULL, 'TMT-EA2B6A2CFB8A4B28', 'Cup Qualifier 9', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.357487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 10, NULL, 'TMT-C5074066E1C94FD1', 'Cup Qualifier 10', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.358487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 11, NULL, 'TMT-7A3F1277628D46AE', 'Cup Qualifier 11', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.359487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 12, NULL, 'TMT-5C707CAC2CEB4EE7', 'Cup Qualifier 12', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.360487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 13, NULL, 'TMT-954F85645AFC44BE', 'Cup Qualifier 13', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.360487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 14, NULL, 'TMT-2687225014A9451E', 'Cup Qualifier 14', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.361489', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 15, NULL, 'TMT-7CEBF67992BB472C', 'Cup Qualifier 15', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.362481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 16, NULL, 'TMT-2F7B759A69784E3B', 'Cup Qualifier 16', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.363486', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 17, NULL, 'TMT-DC0F1AADADD84C8E', 'Cup Qualifier 17', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.364481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 18, NULL, 'TMT-7F596131598D4039', 'Cup Qualifier 18', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.364481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 19, NULL, 'TMT-A58E8FBAE8234EF8', 'Cup Qualifier 19', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.365487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 20, NULL, 'TMT-E1CF886FF780454C', 'Cup Qualifier 20', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.366487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 21, NULL, 'TMT-DD61106D0C1D4111', 'Cup Qualifier 21', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.367481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 22, NULL, 'TMT-1F99B73841884B75', 'Cup Qualifier 22', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.368481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 23, NULL, 'TMT-CA80C5B550C64E7B', 'Cup Qualifier 23', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.368481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 24, NULL, 'TMT-9ABF4C97FE6C401F', 'Cup Qualifier 24', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.369482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 25, NULL, 'TMT-A26DA01C77224D57', 'Cup Qualifier 25', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.370483', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 26, NULL, 'TMT-BAE3205B33B44687', 'Cup Qualifier 26', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.372482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 27, NULL, 'TMT-6C50206031DF4C8B', 'Cup Qualifier 27', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.373481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 28, NULL, 'TMT-173A03FD87D74693', 'Cup Qualifier 28', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.373481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 29, NULL, 'TMT-D5C136C9013C4500', 'Cup Qualifier 29', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.374481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 30, NULL, 'TMT-0F14875706664BF3', 'Cup Qualifier 30', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.375480', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 31, NULL, 'TMT-9FA6E267A0A34EC4', 'Cup Qualifier 31', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.376481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 32, NULL, 'TMT-793F2553DE1C4708', 'Cup Qualifier 32', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.377481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 33, NULL, 'TMT-DF6978AAC848419B', 'Cup Qualifier 33', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.377481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 34, NULL, 'TMT-8E8DC85AA6A54B35', 'Cup Qualifier 34', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.378488', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 35, NULL, 'TMT-456439D708834B8D', 'Cup Qualifier 35', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.379481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 36, NULL, 'TMT-2392AFA552C74125', 'Cup Qualifier 36', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.380481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 37, NULL, 'TMT-3549394EB0BE45D6', 'Cup Qualifier 37', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.381481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 38, NULL, 'TMT-6E1B885CDB704C7E', 'Cup Qualifier 38', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.382480', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(105, 105, 22, 39, NULL, 'TMT-193FD1A10A784198', 'Cup Qualifier 39', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.382480', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 1, NULL, 1, 3, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:3', '2026-09-01 09:55:19.351481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 2, NULL, 2, 4, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:4', '2026-09-01 09:55:19.352487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 3, NULL, 3, 5, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:5', '2026-09-01 09:55:19.352487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 4, NULL, 4, 6, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:6', '2026-09-01 09:55:19.353487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 5, NULL, 5, 7, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:7', '2026-09-01 09:55:19.354485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 6, NULL, 6, 8, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:8', '2026-09-01 09:55:19.355483', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 7, NULL, 7, 9, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:9', '2026-09-01 09:55:19.356487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 8, NULL, 8, 10, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:10', '2026-09-01 09:55:19.357487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 9, NULL, 9, 11, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:11', '2026-09-01 09:55:19.358487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 10, NULL, 10, 12, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:12', '2026-09-01 09:55:19.358487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 11, NULL, 11, 13, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:13', '2026-09-01 09:55:19.359487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 12, NULL, 12, 14, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:14', '2026-09-01 09:55:19.360487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 13, NULL, 13, 15, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:15', '2026-09-01 09:55:19.361489', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 14, NULL, 14, 16, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:16', '2026-09-01 09:55:19.362481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 15, NULL, 15, 17, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:17', '2026-09-01 09:55:19.363486', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 16, NULL, 16, 18, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:18', '2026-09-01 09:55:19.363486', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 17, NULL, 17, 19, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:19', '2026-09-01 09:55:19.364481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 18, NULL, 18, 20, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:20', '2026-09-01 09:55:19.365487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 19, NULL, 19, 21, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:21', '2026-09-01 09:55:19.366487', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 20, NULL, 20, 22, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:22', '2026-09-01 09:55:19.367481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 21, NULL, 21, 23, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:23', '2026-09-01 09:55:19.367481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 22, NULL, 22, 24, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:24', '2026-09-01 09:55:19.368481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 23, NULL, 23, 25, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:25', '2026-09-01 09:55:19.369482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 24, NULL, 24, 26, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:26', '2026-09-01 09:55:19.370483', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 25, NULL, 25, 27, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:27', '2026-09-01 09:55:19.371484', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 26, NULL, 26, 28, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:28', '2026-09-01 09:55:19.372482', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 27, NULL, 27, 29, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:29', '2026-09-01 09:55:19.373481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 28, NULL, 28, 30, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:30', '2026-09-01 09:55:19.374481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 29, NULL, 29, 31, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:31', '2026-09-01 09:55:19.375480', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 30, NULL, 30, 32, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:32', '2026-09-01 09:55:19.375480', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 31, NULL, 31, 33, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:33', '2026-09-01 09:55:19.376481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 32, NULL, 32, 34, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:34', '2026-09-01 09:55:19.377481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 33, NULL, 33, 35, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:35', '2026-09-01 09:55:19.378488', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 34, NULL, 34, 36, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:36', '2026-09-01 09:55:19.379481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 35, NULL, 35, 37, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:37', '2026-09-01 09:55:19.380481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 36, NULL, 36, 38, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:38', '2026-09-01 09:55:19.380481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 37, NULL, 37, 39, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:39', '2026-09-01 09:55:19.381481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 38, NULL, 38, 40, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:40', '2026-09-01 09:55:19.382480', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 39, NULL, 39, 41, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:41', '2026-09-01 09:55:19.383490', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 40, NULL, 40, 42, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:42', '2026-09-01 09:55:19.384481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(106, 106, 16, 41, NULL, 41, 43, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:43', '2026-09-01 09:55:19.385485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 1, NULL, 65, 3, 'active', 'completed', NULL, NULL, 0, 'cup_qualification', 1, 0, '2026-09-01 09:55:19.672967', '2026-09-01 09:55:19.672967', 0, NULL, 'Cup qualification #1', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 2, NULL, 65, 4, 'eliminated', 'completed', NULL, NULL, 0, 'cup_qualification', 8, 0, '2026-09-01 09:55:19.672967', '2026-09-01 09:55:19.673972', 0, NULL, 'Cup qualification #2', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 3, NULL, 65, 5, 'active', 'completed', NULL, NULL, 0, 'cup_qualification', 2, 0, '2026-09-01 09:55:19.673972', '2026-09-01 09:55:19.673972', 0, NULL, 'Cup qualification #3', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 4, NULL, 65, 6, 'eliminated', 'completed', NULL, NULL, 0, 'cup_qualification', 7, 0, '2026-09-01 09:55:19.673972', '2026-09-01 09:55:19.673972', 0, NULL, 'Cup qualification #4', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 5, NULL, 65, 7, 'active', 'completed', NULL, NULL, 0, 'cup_qualification', 3, 0, '2026-09-01 09:55:19.673972', '2026-09-01 09:55:19.673972', 0, NULL, 'Cup qualification #5', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 6, NULL, 65, 8, 'eliminated', 'completed', NULL, NULL, 0, 'cup_qualification', 6, 0, '2026-09-01 09:55:19.674968', '2026-09-01 09:55:19.674968', 0, NULL, 'Cup qualification #6', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 7, NULL, 65, 9, 'active', 'completed', NULL, NULL, 0, 'cup_qualification', 4, 0, '2026-09-01 09:55:19.674968', '2026-09-01 09:55:19.674968', 0, NULL, 'Cup qualification #7', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 8, NULL, 65, 10, 'eliminated', 'completed', NULL, NULL, 0, 'cup_qualification', 5, 0, '2026-09-01 09:55:19.674968', '2026-09-01 09:55:19.674968', 0, NULL, 'Cup qualification #8', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 9, NULL, 65, 11, 'eliminated', 'completed', NULL, NULL, 0, 'cup_qualification', 9, 0, '2026-09-01 09:55:19.675966', '2026-09-01 09:55:19.675966', 0, NULL, 'Cup qualification #9', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 10, NULL, 65, 12, 'eliminated', 'completed', NULL, NULL, 0, 'cup_qualification', 10, 0, '2026-09-01 09:55:19.675966', '2026-09-01 09:55:19.675966', 0, NULL, 'Cup qualification #10', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 11, NULL, 65, 13, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.675966', '2026-09-01 09:55:19.675966', 0, NULL, 'Cup qualification #11', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 12, NULL, 65, 14, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.675966', '2026-09-01 09:55:19.675966', 0, NULL, 'Cup qualification #12', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 13, NULL, 65, 15, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.676967', '2026-09-01 09:55:19.676967', 0, NULL, 'Cup qualification #13', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 14, NULL, 65, 16, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.676967', '2026-09-01 09:55:19.676967', 0, NULL, 'Cup qualification #14', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 15, NULL, 65, 17, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.676967', '2026-09-01 09:55:19.676967', 0, NULL, 'Cup qualification #15', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 16, NULL, 65, 18, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.677968', '2026-09-01 09:55:19.677968', 0, NULL, 'Cup qualification #16', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 17, NULL, 65, 19, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.677968', '2026-09-01 09:55:19.677968', 0, NULL, 'Cup qualification #17', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 18, NULL, 65, 20, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.677968', '2026-09-01 09:55:19.677968', 0, NULL, 'Cup qualification #18', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 19, NULL, 65, 21, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.677968', '2026-09-01 09:55:19.677968', 0, NULL, 'Cup qualification #19', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 20, NULL, 65, 22, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.678967', '2026-09-01 09:55:19.678967', 0, NULL, 'Cup qualification #20', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 21, NULL, 65, 23, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.678967', '2026-09-01 09:55:19.678967', 0, NULL, 'Cup qualification #21', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 22, NULL, 65, 24, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.678967', '2026-09-01 09:55:19.678967', 0, NULL, 'Cup qualification #22', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 23, NULL, 65, 25, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.678967', '2026-09-01 09:55:19.678967', 0, NULL, 'Cup qualification #23', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 24, NULL, 65, 26, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.679974', '2026-09-01 09:55:19.679974', 0, NULL, 'Cup qualification #24', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 25, NULL, 65, 27, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.679974', '2026-09-01 09:55:19.679974', 0, NULL, 'Cup qualification #25', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 26, NULL, 65, 28, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.679974', '2026-09-01 09:55:19.679974', 0, NULL, 'Cup qualification #26', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 27, NULL, 65, 29, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.679974', '2026-09-01 09:55:19.679974', 0, NULL, 'Cup qualification #27', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 28, NULL, 65, 30, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.679974', '2026-09-01 09:55:19.680972', 0, NULL, 'Cup qualification #28', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 29, NULL, 65, 31, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.680972', '2026-09-01 09:55:19.680972', 0, NULL, 'Cup qualification #29', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(107, 107, 16, 30, NULL, 65, 32, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.680972', '2026-09-01 09:55:19.680972', 0, NULL, 'Cup qualification #30', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 42, NULL, 42, 44, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:44', '2026-09-01 09:55:19.385485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 43, NULL, 43, 45, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:45', '2026-09-01 09:55:19.386481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 44, NULL, 44, 46, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:46', '2026-09-01 09:55:19.387485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 45, NULL, 45, 47, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:47', '2026-09-01 09:55:19.388485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 46, NULL, 46, 48, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:48', '2026-09-01 09:55:19.389714', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 47, NULL, 47, 49, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:49', '2026-09-01 09:55:19.390717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 48, NULL, 48, 50, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:50', '2026-09-01 09:55:19.390717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 49, NULL, 49, 51, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:51', '2026-09-01 09:55:19.391716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 50, NULL, 50, 52, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:52', '2026-09-01 09:55:19.392716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 51, NULL, 51, 53, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:53', '2026-09-01 09:55:19.393716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 52, NULL, 52, 54, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:54', '2026-09-01 09:55:19.394716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 53, NULL, 53, 55, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:55', '2026-09-01 09:55:19.395716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 54, NULL, 54, 56, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:56', '2026-09-01 09:55:19.395716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 55, NULL, 55, 57, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:57', '2026-09-01 09:55:19.396716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 56, NULL, 56, 58, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:58', '2026-09-01 09:55:19.397716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 57, NULL, 57, 59, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:59', '2026-09-01 09:55:19.398717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 58, NULL, 58, 60, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:60', '2026-09-01 09:55:19.399716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 59, NULL, 59, 61, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:61', '2026-09-01 09:55:19.400716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 60, NULL, 60, 62, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:62', '2026-09-01 09:55:19.400716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 61, NULL, 61, 63, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:63', '2026-09-01 09:55:19.401716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 62, NULL, 62, 64, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:64', '2026-09-01 09:55:19.402717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 63, NULL, 63, 65, '2026', 'umshova-cup-pilot', 'qualified', 'umshova-cup-pilot:65', '2026-09-01 09:55:19.403719', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(108, 108, 16, 64, NULL, 64, 66, '2026', 'umshova-cup-pilot', 'checked_in', 'umshova-cup-pilot:66', '2026-09-01 09:55:19.404717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 31, NULL, 65, 33, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.680972', '2026-09-01 09:55:19.680972', 0, NULL, 'Cup qualification #31', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 32, NULL, 65, 34, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.681972', '2026-09-01 09:55:19.681972', 0, NULL, 'Cup qualification #32', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 33, NULL, 65, 35, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.681972', '2026-09-01 09:55:19.681972', 0, NULL, 'Cup qualification #33', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 34, NULL, 65, 36, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.681972', '2026-09-01 09:55:19.681972', 0, NULL, 'Cup qualification #34', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 35, NULL, 65, 37, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.681972', '2026-09-01 09:55:19.681972', 0, NULL, 'Cup qualification #35', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 36, NULL, 65, 38, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.681972', '2026-09-01 09:55:19.682971', 0, NULL, 'Cup qualification #36', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 37, NULL, 65, 39, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.682971', '2026-09-01 09:55:19.682971', 0, NULL, 'Cup qualification #37', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 38, NULL, 65, 40, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.682971', '2026-09-01 09:55:19.682971', 0, NULL, 'Cup qualification #38', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 39, NULL, 65, 41, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.682971', '2026-09-01 09:55:19.682971', 0, NULL, 'Cup qualification #39', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 40, NULL, 65, 42, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.682971', '2026-09-01 09:55:19.683966', 0, NULL, 'Cup qualification #40', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 41, NULL, 65, 43, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.683966', '2026-09-01 09:55:19.683966', 0, NULL, 'Cup qualification #41', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 42, NULL, 65, 44, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.683966', '2026-09-01 09:55:19.683966', 0, NULL, 'Cup qualification #42', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 43, NULL, 65, 45, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.683966', '2026-09-01 09:55:19.683966', 0, NULL, 'Cup qualification #43', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 44, NULL, 65, 46, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.683966', '2026-09-01 09:55:19.683966', 0, NULL, 'Cup qualification #44', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 45, NULL, 65, 47, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.684971', '2026-09-01 09:55:19.684971', 0, NULL, 'Cup qualification #45', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 46, NULL, 65, 48, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.684971', '2026-09-01 09:55:19.684971', 0, NULL, 'Cup qualification #46', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 47, NULL, 65, 49, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.684971', '2026-09-01 09:55:19.684971', 0, NULL, 'Cup qualification #47', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 48, NULL, 65, 50, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.684971', '2026-09-01 09:55:19.684971', 0, NULL, 'Cup qualification #48', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 49, NULL, 65, 51, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.685972', '2026-09-01 09:55:19.685972', 0, NULL, 'Cup qualification #49', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 50, NULL, 65, 52, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.685972', '2026-09-01 09:55:19.685972', 0, NULL, 'Cup qualification #50', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 51, NULL, 65, 53, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.685972', '2026-09-01 09:55:19.685972', 0, NULL, 'Cup qualification #51', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 52, NULL, 65, 54, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.685972', '2026-09-01 09:55:19.685972', 0, NULL, 'Cup qualification #52', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 53, NULL, 65, 55, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.685972', '2026-09-01 09:55:19.686968', 0, NULL, 'Cup qualification #53', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 54, NULL, 65, 56, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.686968', '2026-09-01 09:55:19.686968', 0, NULL, 'Cup qualification #54', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 55, NULL, 65, 57, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.686968', '2026-09-01 09:55:19.686968', 0, NULL, 'Cup qualification #55', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 56, NULL, 65, 58, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.686968', '2026-09-01 09:55:19.686968', 0, NULL, 'Cup qualification #56', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 57, NULL, 65, 59, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.687974', '2026-09-01 09:55:19.687974', 0, NULL, 'Cup qualification #57', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 58, NULL, 65, 60, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.687974', '2026-09-01 09:55:19.687974', 0, NULL, 'Cup qualification #58', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 59, NULL, 65, 61, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.687974', '2026-09-01 09:55:19.687974', 0, NULL, 'Cup qualification #59', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(109, 109, 16, 60, NULL, 65, 62, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.687974', '2026-09-01 09:55:19.687974', 0, NULL, 'Cup qualification #60', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 40, NULL, 'TMT-01FE100D7ED6436C', 'Cup Qualifier 40', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.383490', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 41, NULL, 'TMT-2C6E9D81E30F40C2', 'Cup Qualifier 41', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.384481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 42, NULL, 'TMT-24CFF832DB7543C3', 'Cup Qualifier 42', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.385485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 43, NULL, 'TMT-17722F2EC90D4757', 'Cup Qualifier 43', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.386481', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 44, NULL, 'TMT-D87FEA5B426E435D', 'Cup Qualifier 44', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.387485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 45, NULL, 'TMT-9AF3E0277E2B4E8F', 'Cup Qualifier 45', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.388485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 46, NULL, 'TMT-13F9FE59D184401C', 'Cup Qualifier 46', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.388485', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 47, NULL, 'TMT-82586BDAE66A4D70', 'Cup Qualifier 47', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.389714', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 48, NULL, 'TMT-66E3286F9D834919', 'Cup Qualifier 48', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.390717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 49, NULL, 'TMT-232A239DD3544E2C', 'Cup Qualifier 49', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.391716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 50, NULL, 'TMT-192118786AAD4F55', 'Cup Qualifier 50', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.392716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 51, NULL, 'TMT-19B1CB2CEC6E4F04', 'Cup Qualifier 51', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.393716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 52, NULL, 'TMT-A3E8276A5BAF417D', 'Cup Qualifier 52', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.393716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 53, NULL, 'TMT-BF255885B6104709', 'Cup Qualifier 53', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.394716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 54, NULL, 'TMT-C81DEF148F52464F', 'Cup Qualifier 54', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.395716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 55, NULL, 'TMT-61D4B959CECD42AB', 'Cup Qualifier 55', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.396716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 56, NULL, 'TMT-2F6AEE175EC54D19', 'Cup Qualifier 56', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.397716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 57, NULL, 'TMT-C0463344CC0A436B', 'Cup Qualifier 57', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.397716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 58, NULL, 'TMT-BA79E63B8B334E69', 'Cup Qualifier 58', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.398717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 59, NULL, 'TMT-08CD5BE22C2842F9', 'Cup Qualifier 59', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.399716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 60, NULL, 'TMT-A1849CA1D19A428F', 'Cup Qualifier 60', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.400716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 61, NULL, 'TMT-823A461512D64876', 'Cup Qualifier 61', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.401716', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 62, NULL, 'TMT-2601042D401547D1', 'Cup Qualifier 62', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.402717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 63, NULL, 'TMT-10587C9A544942A6', 'Cup Qualifier 63', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.403719', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 64, NULL, 'TMT-C496109C4ABC4B60', 'Cup Qualifier 64', 'standard', 1, 10, 10, 4, 1, 'open', 0, NULL, NULL, '2026-09-01 09:55:19.404717', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(110, 110, 22, 65, NULL, 'TMT-918451316C6D48C9', 'uMshova Cup', 'cup', 1, 0, 0, 64, 64, 'completed', 1, 64, '2026-09-01 09:55:19.671971', '2026-09-01 09:55:19.670968', '2026-09-01 09:55:19.709223', '2026-09-01 09:55:19.776228', NULL, NULL, 3, 5, 7, '{"event_key": "umshova-cup-pilot", "season": "2026", "qualification_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64], "cash_payouts_enabled": false}');
INSERT INTO lost_and_found VALUES(111, 111, 13, 1, NULL, 65, 1, 'Round of 64', 1, 48, 15, 1, 'scheduled', NULL, '2026-09-01 09:55:19.691222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 2, NULL, 65, 1, 'Round of 64', 2, 47, 39, 2, 'scheduled', NULL, '2026-09-01 09:55:19.692221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 3, NULL, 65, 1, 'Round of 64', 3, 64, 58, 3, 'scheduled', NULL, '2026-09-01 09:55:19.692221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 4, NULL, 65, 1, 'Round of 64', 4, 38, 62, 4, 'scheduled', NULL, '2026-09-01 09:55:19.692221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 5, NULL, 65, 1, 'Round of 64', 5, 9, 49, 5, 'scheduled', NULL, '2026-09-01 09:55:19.693221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 6, NULL, 65, 1, 'Round of 64', 6, 35, 45, 6, 'scheduled', NULL, '2026-09-01 09:55:19.693221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 7, NULL, 65, 1, 'Round of 64', 7, 50, 43, 7, 'scheduled', NULL, '2026-09-01 09:55:19.694221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 8, NULL, 65, 1, 'Round of 64', 8, 61, 60, 8, 'scheduled', NULL, '2026-09-01 09:55:19.694221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 9, NULL, 65, 1, 'Round of 64', 9, 37, 29, 9, 'scheduled', NULL, '2026-09-01 09:55:19.694221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 10, NULL, 65, 1, 'Round of 64', 10, 51, 55, 10, 'scheduled', NULL, '2026-09-01 09:55:19.695222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 11, NULL, 65, 1, 'Round of 64', 11, 57, 17, 11, 'scheduled', NULL, '2026-09-01 09:55:19.695222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 12, NULL, 65, 1, 'Round of 64', 12, 10, 59, 12, 'scheduled', NULL, '2026-09-01 09:55:19.695222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 13, NULL, 65, 1, 'Round of 64', 13, 22, 28, 13, 'scheduled', NULL, '2026-09-01 09:55:19.696222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 14, NULL, 65, 1, 'Round of 64', 14, 21, 12, 14, 'scheduled', NULL, '2026-09-01 09:55:19.696222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 15, NULL, 65, 1, 'Round of 64', 15, 31, 25, 15, 'scheduled', NULL, '2026-09-01 09:55:19.696222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 16, NULL, 65, 1, 'Round of 64', 16, 53, 41, 16, 'scheduled', NULL, '2026-09-01 09:55:19.697222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 17, NULL, 65, 1, 'Round of 64', 17, 11, 44, 17, 'scheduled', NULL, '2026-09-01 09:55:19.697222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 18, NULL, 65, 1, 'Round of 64', 18, 4, 34, 18, 'scheduled', NULL, '2026-09-01 09:55:19.697222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 19, NULL, 65, 1, 'Round of 64', 19, 33, 27, 19, 'scheduled', NULL, '2026-09-01 09:55:19.698230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 20, NULL, 65, 1, 'Round of 64', 20, 52, 65, 20, 'scheduled', NULL, '2026-09-01 09:55:19.698230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 21, NULL, 65, 1, 'Round of 64', 21, 32, 63, 21, 'scheduled', NULL, '2026-09-01 09:55:19.698230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 22, NULL, 65, 1, 'Round of 64', 22, 18, 20, 22, 'scheduled', NULL, '2026-09-01 09:55:19.699222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 23, NULL, 65, 1, 'Round of 64', 23, 16, 5, 23, 'scheduled', NULL, '2026-09-01 09:55:19.699222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 24, NULL, 65, 1, 'Round of 64', 24, 3, 23, 24, 'scheduled', NULL, '2026-09-01 09:55:19.700223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 25, NULL, 65, 1, 'Round of 64', 25, 24, 42, 25, 'scheduled', NULL, '2026-09-01 09:55:19.700223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 26, NULL, 65, 1, 'Round of 64', 26, 14, 56, 26, 'scheduled', NULL, '2026-09-01 09:55:19.700223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 27, NULL, 65, 1, 'Round of 64', 27, 40, 54, 27, 'scheduled', NULL, '2026-09-01 09:55:19.701221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 28, NULL, 65, 1, 'Round of 64', 28, 36, 13, 28, 'scheduled', NULL, '2026-09-01 09:55:19.701221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 29, NULL, 65, 1, 'Round of 64', 29, 6, 7, 29, 'scheduled', NULL, '2026-09-01 09:55:19.701221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 30, NULL, 65, 1, 'Round of 64', 30, 19, 26, 30, 'scheduled', NULL, '2026-09-01 09:55:19.702221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 31, NULL, 65, 1, 'Round of 64', 31, 66, 30, 31, 'scheduled', NULL, '2026-09-01 09:55:19.702221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 32, NULL, 65, 1, 'Round of 64', 32, 8, 46, 32, 'scheduled', NULL, '2026-09-01 09:55:19.702221', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 33, NULL, 65, 2, 'Round of 32', 1, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.703230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 34, NULL, 65, 2, 'Round of 32', 2, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.703230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 35, NULL, 65, 2, 'Round of 32', 3, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.703230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 36, NULL, 65, 2, 'Round of 32', 4, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.703230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 37, NULL, 65, 2, 'Round of 32', 5, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.703230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 38, NULL, 65, 2, 'Round of 32', 6, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.703230', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 39, NULL, 65, 2, 'Round of 32', 7, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.704222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 40, NULL, 65, 2, 'Round of 32', 8, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.704222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 41, NULL, 65, 2, 'Round of 32', 9, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.704222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 42, NULL, 65, 2, 'Round of 32', 10, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.704222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 43, NULL, 65, 2, 'Round of 32', 11, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.705222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 44, NULL, 65, 2, 'Round of 32', 12, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.705222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 45, NULL, 65, 2, 'Round of 32', 13, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.705222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 46, NULL, 65, 2, 'Round of 32', 14, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.705222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 47, NULL, 65, 2, 'Round of 32', 15, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.705222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 48, NULL, 65, 2, 'Round of 32', 16, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.705222', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 49, NULL, 65, 3, 'Round of 16', 1, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 50, NULL, 65, 3, 'Round of 16', 2, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 51, NULL, 65, 3, 'Round of 16', 3, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 52, NULL, 65, 3, 'Round of 16', 4, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 53, NULL, 65, 3, 'Round of 16', 5, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 54, NULL, 65, 3, 'Round of 16', 6, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 55, NULL, 65, 3, 'Round of 16', 7, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.706225', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 56, NULL, 65, 3, 'Round of 16', 8, NULL, NULL, NULL, 'pending', NULL, '2026-09-01 09:55:19.707223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 57, NULL, 65, 4, 'Quarter-Final', 1, 3, 4, 33, 'completed', 3, '2026-09-01 09:55:19.707223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 58, NULL, 65, 4, 'Quarter-Final', 2, 5, 6, 34, 'completed', 5, '2026-09-01 09:55:19.707223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 59, NULL, 65, 4, 'Quarter-Final', 3, 7, 8, 35, 'completed', 7, '2026-09-01 09:55:19.707223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(111, 111, 13, 60, NULL, 65, 4, 'Quarter-Final', 4, 9, 10, 36, 'completed', 9, '2026-09-01 09:55:19.707223', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 34, NULL, 'cup_player_31', 'cup_player_31@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.376481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 35, NULL, 'cup_player_32', 'cup_player_32@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.377481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 36, NULL, 'cup_player_33', 'cup_player_33@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.378488', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 37, NULL, 'cup_player_34', 'cup_player_34@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.379481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 38, NULL, 'cup_player_35', 'cup_player_35@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.380481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 39, NULL, 'cup_player_36', 'cup_player_36@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.380481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 40, NULL, 'cup_player_37', 'cup_player_37@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.381481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 41, NULL, 'cup_player_38', 'cup_player_38@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.382480', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 42, NULL, 'cup_player_39', 'cup_player_39@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.383490', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 43, NULL, 'cup_player_40', 'cup_player_40@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.384481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 44, NULL, 'cup_player_41', 'cup_player_41@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.384481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 45, NULL, 'cup_player_42', 'cup_player_42@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.385485', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 46, NULL, 'cup_player_43', 'cup_player_43@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.386481', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 47, NULL, 'cup_player_44', 'cup_player_44@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.387485', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 48, NULL, 'cup_player_45', 'cup_player_45@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.388485', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 49, NULL, 'cup_player_46', 'cup_player_46@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.389714', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 50, NULL, 'cup_player_47', 'cup_player_47@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.390717', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 51, NULL, 'cup_player_48', 'cup_player_48@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.390717', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 52, NULL, 'cup_player_49', 'cup_player_49@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.391716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 53, NULL, 'cup_player_50', 'cup_player_50@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.392716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 54, NULL, 'cup_player_51', 'cup_player_51@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.393716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 55, NULL, 'cup_player_52', 'cup_player_52@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.394716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 56, NULL, 'cup_player_53', 'cup_player_53@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.395716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 57, NULL, 'cup_player_54', 'cup_player_54@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.395716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 58, NULL, 'cup_player_55', 'cup_player_55@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.396716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 59, NULL, 'cup_player_56', 'cup_player_56@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.397716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 60, NULL, 'cup_player_57', 'cup_player_57@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.398717', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 61, NULL, 'cup_player_58', 'cup_player_58@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.399716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 62, NULL, 'cup_player_59', 'cup_player_59@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.400716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 63, NULL, 'cup_player_60', 'cup_player_60@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.400716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 64, NULL, 'cup_player_61', 'cup_player_61@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.401716', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 65, NULL, 'cup_player_62', 'cup_player_62@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.402717', NULL);
INSERT INTO lost_and_found VALUES(112, 112, 22, 66, NULL, 'cup_player_63', 'cup_player_63@test.com', NULL, 'not-used', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'not_submitted', NULL, 1, 0, 0, 0, '2026-09-01 11:55:19.403719', NULL);
INSERT INTO lost_and_found VALUES(113, 113, 16, 61, NULL, 65, 63, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.688967', '2026-09-01 09:55:19.688967', 0, NULL, 'Cup qualification #61', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(113, 113, 16, 62, NULL, 65, 64, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.689221', '2026-09-01 09:55:19.689221', 0, NULL, 'Cup qualification #62', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(113, 113, 16, 63, NULL, 65, 65, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.689221', '2026-09-01 09:55:19.689221', 0, NULL, 'Cup qualification #63', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO lost_and_found VALUES(113, 113, 16, 64, NULL, 65, 66, 'registered', 'completed', NULL, NULL, 0, 'cup_qualification', NULL, 0, '2026-09-01 09:55:19.689221', '2026-09-01 09:55:19.689221', 0, NULL, 'Cup qualification #64', NULL, NULL, NULL, NULL, NULL, NULL);
PRAGMA writable_schema = off;
COMMIT;
