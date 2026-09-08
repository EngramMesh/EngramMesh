CREATE TABLE IF NOT EXISTS memory_claim_proposals (
    tenant_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    episode_id uuid NOT NULL,
    subject_id uuid NOT NULL,
    workspace_id text,
    agent_id uuid,
    subject text NOT NULL,
    predicate text NOT NULL,
    object_value text NOT NULL,
    polarity boolean NOT NULL,
    epistemic_kind text NOT NULL,
    confidence double precision NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    recorded_from timestamptz NOT NULL,
    recorded_to timestamptz,
    status text NOT NULL,
    evidence jsonb NOT NULL,
    extractor_version text NOT NULL,
    PRIMARY KEY (tenant_id, claim_id),
    CONSTRAINT memory_claim_proposals_episode_fkey
        FOREIGN KEY (tenant_id, episode_id)
        REFERENCES memory_episodes (tenant_id, episode_id),
    CONSTRAINT memory_claim_proposals_epistemic_kind_check CHECK (
        epistemic_kind IN ('observed', 'extracted', 'inferred', 'human_confirmed')
    ),
    CONSTRAINT memory_claim_proposals_status_check CHECK (
        status IN ('proposed', 'accepted', 'disputed', 'retracted', 'superseded')
    ),
    CONSTRAINT memory_claim_proposals_confidence_check CHECK (
        confidence >= 0 AND confidence <= 1
    ),
    UNIQUE (tenant_id, episode_id, extractor_version)
);

CREATE INDEX IF NOT EXISTS memory_claim_proposals_scope_recorded_idx
    ON memory_claim_proposals (
        tenant_id,
        subject_id,
        recorded_from DESC,
        claim_id DESC
    );
