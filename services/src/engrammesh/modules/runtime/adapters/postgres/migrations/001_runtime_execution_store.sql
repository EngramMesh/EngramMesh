CREATE TABLE IF NOT EXISTS runtime_start_idempotency (
    tenant_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    execution_id uuid NOT NULL,
    fingerprint jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS runtime_execution_snapshots (
    tenant_id uuid NOT NULL,
    execution_id uuid NOT NULL,
    subject_id uuid NOT NULL,
    workspace_id text,
    agent_id uuid,
    revision integer NOT NULL,
    status text NOT NULL,
    snapshot jsonb NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, execution_id),
    CONSTRAINT runtime_execution_snapshots_status_check CHECK (
        status IN (
            'pending', 'planning', 'running', 'waiting', 'retrying',
            'cancelling', 'compensating', 'succeeded', 'failed', 'cancelled'
        )
    )
);

CREATE INDEX IF NOT EXISTS runtime_execution_snapshots_tenant_subject_updated_idx
    ON runtime_execution_snapshots (tenant_id, subject_id, updated_at DESC);
