CREATE TABLE IF NOT EXISTS runtime_outbox_events (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    tenant_id uuid NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_version integer NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz
);

CREATE INDEX IF NOT EXISTS runtime_outbox_events_tenant_occurred_event_idx
    ON runtime_outbox_events (tenant_id, occurred_at ASC, event_id ASC);
