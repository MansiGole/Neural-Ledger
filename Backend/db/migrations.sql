-- Backend/db/migrations.sql
-- Add the replay_events table for tracking AI Security responses (Twist 2)

CREATE TABLE IF NOT EXISTS replay_events (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    fraud_probability FLOAT NOT NULL,
    is_blocked BOOLEAN NOT NULL DEFAULT TRUE,
    timing_delta_ms BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Ensure we index transaction queries for high throughput
CREATE INDEX IF NOT EXISTS idx_replay_events_txn_id ON replay_events(transaction_id);
