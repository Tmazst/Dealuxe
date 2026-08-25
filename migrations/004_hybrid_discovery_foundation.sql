-- Version 3 Hybrid MVP foundation. Profile data remains private and inactive
-- unless both HYBRID_ENABLED and HYBRID_PROFILE_ENABLED are explicitly true.
CREATE TABLE IF NOT EXISTS discovery_profiles (
    id INTEGER NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT 0,
    intent VARCHAR(30),
    category VARCHAR(50),
    subcategory VARCHAR(80),
    location VARCHAR(120),
    predefined_caption VARCHAR(80),
    custom_caption VARCHAR(280),
    moderation_status VARCHAR(30) NOT NULL DEFAULT 'not_required',
    is_visible BOOLEAN NOT NULL DEFAULT 0,
    chat_preference_enabled BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_discovery_profiles_user_id UNIQUE (user_id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_discovery_profiles_visibility
    ON discovery_profiles (is_visible);
CREATE INDEX IF NOT EXISTS idx_discovery_profiles_moderation
    ON discovery_profiles (moderation_status);
