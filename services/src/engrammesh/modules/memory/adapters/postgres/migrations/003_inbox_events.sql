CREATE TABLE IF NOT EXISTS memory_inbox_events (
    event_id uuid PRIMARY KEY,
    consumer_name text NOT NULL,
    event_type text NOT NULL,
    tenant_id uuid NOT NULL,
    processed_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS memory_inbox_events_tenant_processed_idx
    ON memory_inbox_events (tenant_id, processed_at DESC);
