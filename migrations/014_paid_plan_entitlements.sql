-- Configurable paid-plan switches, purchase lifecycle and expiring access.

CREATE TABLE IF NOT EXISTS pricing_feature_settings (
    id INTEGER PRIMARY KEY,
    setting_key VARCHAR(80) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT 0,
    updated_by INTEGER REFERENCES users(id),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_purchases (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan_code VARCHAR(30) NOT NULL,
    amount FLOAT NOT NULL,
    duration_days INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'initiated',
    external_ref_id VARCHAR(64) NOT NULL UNIQUE,
    gateway_transaction_id VARCHAR(255) UNIQUE,
    transaction_id INTEGER UNIQUE REFERENCES transactions(id),
    completed_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_purchases_user ON plan_purchases (user_id);
CREATE INDEX IF NOT EXISTS idx_plan_purchases_status ON plan_purchases (status);

CREATE TABLE IF NOT EXISTS plan_entitlements (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan_code VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    purchase_id INTEGER NOT NULL UNIQUE REFERENCES plan_purchases(id),
    starts_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_entitlements_user_status
    ON plan_entitlements (user_id, status);
CREATE INDEX IF NOT EXISTS idx_plan_entitlements_expiry
    ON plan_entitlements (expires_at);
