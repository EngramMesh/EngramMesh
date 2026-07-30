CREATE TABLE IF NOT EXISTS memory_episodes (
    tenant_id uuid NOT NULL,
    episode_id uuid NOT NULL,
    subject_id uuid NOT NULL,
    workspace_id text,
    agent_id uuid,
    actor_id uuid NOT NULL,
    source_type text NOT NULL,
    content_ref uuid NOT NULL,
    observed_at timestamptz NOT NULL,
    ingested_at timestamptz NOT NULL,
    content_hash text NOT NULL,
    idempotency_key text NOT NULL,
    sensitivity text NOT NULL,
    retention_class text NOT NULL,
    consent_basis text NOT NULL,
    PRIMARY KEY (tenant_id, episode_id),
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT memory_episodes_source_type_check CHECK (
        source_type IN ('user', 'agent', 'tool', 'file', 'system')
    ),
    CONSTRAINT memory_episodes_sensitivity_check CHECK (
        sensitivity IN ('public', 'internal', 'confidential', 'restricted')
    ),
    CONSTRAINT memory_episodes_retention_class_check CHECK (
        retention_class IN ('ephemeral', 'standard', 'extended', 'legal_hold')
    )
);

CREATE TABLE IF NOT EXISTS memory_episode_idempotency (
    tenant_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    episode_id uuid NOT NULL,
    subject_id uuid NOT NULL,
    workspace_id text,
    agent_id uuid,
    actor_id uuid NOT NULL,
    source_type text NOT NULL,
    content_ref uuid NOT NULL,
    observed_at timestamptz NOT NULL,
    content_hash text NOT NULL,
    sensitivity text NOT NULL,
    retention_class text NOT NULL,
    consent_basis text NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key),
    CONSTRAINT memory_episode_idempotency_source_type_check CHECK (
        source_type IN ('user', 'agent', 'tool', 'file', 'system')
    ),
    CONSTRAINT memory_episode_idempotency_sensitivity_check CHECK (
        sensitivity IN ('public', 'internal', 'confidential', 'restricted')
    ),
    CONSTRAINT memory_episode_idempotency_retention_class_check CHECK (
        retention_class IN ('ephemeral', 'standard', 'extended', 'legal_hold')
    ),
    CONSTRAINT memory_episode_idempotency_episode_fkey FOREIGN KEY (tenant_id, episode_id)
        REFERENCES memory_episodes (tenant_id, episode_id)
);

CREATE TABLE IF NOT EXISTS memory_outbox_events (
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

CREATE INDEX IF NOT EXISTS memory_outbox_events_tenant_occurred_event_idx
    ON memory_outbox_events (tenant_id, occurred_at ASC, event_id ASC);
