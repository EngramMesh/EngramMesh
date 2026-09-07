CREATE INDEX IF NOT EXISTS runtime_outbox_events_unpublished_order_idx
    ON runtime_outbox_events (occurred_at ASC, event_id ASC)
    WHERE published_at IS NULL;
