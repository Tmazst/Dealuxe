-- Privacy-safe aggregate counters for the Version 3 MVP pilot.
CREATE TABLE IF NOT EXISTS hybrid_pilot_metrics (
    id INTEGER NOT NULL PRIMARY KEY,
    metric_key VARCHAR(80) NOT NULL UNIQUE,
    total_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
