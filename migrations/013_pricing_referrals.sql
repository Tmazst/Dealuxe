-- Version 3 scalable pricing/referral foundation.
-- Pricing definitions remain versioned in pricing/catalog.py; these tables
-- persist universal referral attribution and idempotent E10 rewards.

CREATE TABLE IF NOT EXISTS referral_codes (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    code VARCHAR(20) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_referral_codes_code
    ON referral_codes (code);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY,
    referral_code_id INTEGER NOT NULL REFERENCES referral_codes(id),
    referrer_id INTEGER NOT NULL REFERENCES users(id),
    referred_user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reward_amount FLOAT NOT NULL DEFAULT 10.0,
    first_valid_tournament_id INTEGER REFERENCES tournaments(id),
    reward_transaction_id INTEGER UNIQUE REFERENCES transactions(id),
    qualified_at DATETIME,
    rewarded_at DATETIME,
    created_at DATETIME NOT NULL,
    CONSTRAINT ck_referrals_not_self CHECK (referrer_id != referred_user_id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer
    ON referrals (referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_status
    ON referrals (status);
