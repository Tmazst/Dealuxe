-- Apply once to an existing production database before deploying the model changes.
-- Existing tournaments retain six starting cards and five minutes per turn.
ALTER TABLE tournaments ADD COLUMN card_count INTEGER NOT NULL DEFAULT 6;
ALTER TABLE tournaments ADD COLUMN turn_duration_seconds INTEGER NOT NULL DEFAULT 300;
