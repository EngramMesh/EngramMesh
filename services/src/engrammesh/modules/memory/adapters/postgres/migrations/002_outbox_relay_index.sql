CREATE INDEX IF NOT EXISTS memory_outbox_events_unpublished_order_idx
    ON memory_outbox_events (occurred_at ASC, event_id ASC)
    WHERE published_at IS NULL;
