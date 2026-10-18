-- Initial PostgreSQL schema. Applied explicitly by TaskEngine.migrate().
-- The schema is namespaced to avoid creating tables in public.

CREATE TABLE IF NOT EXISTS task_engine.jobs (
    id UUID PRIMARY KEY,
    task_name TEXT NOT NULL,
    task_version INTEGER NOT NULL CHECK (task_version >= 1),
    queue TEXT NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'retry_scheduled', 'succeeded', 'failed', 'cancelled')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    scheduled_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ,
    first_started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    attempts_count INTEGER NOT NULL DEFAULT 0 CHECK (attempts_count >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts >= 1),
    timeout_interval INTERVAL NOT NULL CHECK (timeout_interval > INTERVAL '0 seconds'),
    retry_delay_interval INTERVAL NOT NULL CHECK (retry_delay_interval > INTERVAL '0 seconds'),
    current_attempt_id UUID,
    result_present BOOLEAN NOT NULL DEFAULT FALSE,
    result JSONB,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    idempotency_key VARCHAR(128),
    intent_sha256 CHAR(64) NOT NULL,
    CONSTRAINT job_status_fields_consistent CHECK (
        (
            status IN ('queued', 'retry_scheduled')
            AND available_at IS NOT NULL
            AND current_attempt_id IS NULL
            AND finished_at IS NULL
        ) OR (
            status = 'running'
            AND available_at IS NULL
            AND current_attempt_id IS NOT NULL
            AND finished_at IS NULL
        ) OR (
            status IN ('succeeded', 'failed', 'cancelled')
            AND available_at IS NULL
            AND current_attempt_id IS NULL
            AND finished_at IS NOT NULL
        )
    ),
    CONSTRAINT job_result_only_on_success CHECK (
        (status = 'succeeded' AND result_present AND result IS NOT NULL)
        OR (status <> 'succeeded' AND NOT result_present AND result IS NULL)
    ),
    CONSTRAINT attempts_within_limit CHECK (attempts_count <= max_attempts)
);

CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotency_key_uniq
    ON task_engine.jobs (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS jobs_ready_by_queue_idx
    ON task_engine.jobs (queue, available_at, created_at)
    WHERE status IN ('queued', 'retry_scheduled');

CREATE TABLE IF NOT EXISTS task_engine.attempts (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES task_engine.jobs(id) ON DELETE CASCADE,
    number INTEGER NOT NULL CHECK (number >= 1),
    worker_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('claimed', 'running', 'succeeded', 'failed', 'timed_out', 'lost')
    ),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    started_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    lease_expires_at TIMESTAMPTZ NOT NULL,
    deadline_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    execution_duration_ms BIGINT CHECK (execution_duration_ms >= 0),
    error_code TEXT,
    error_message VARCHAR(512),
    exception_type TEXT,
    UNIQUE (job_id, number)
);

CREATE INDEX IF NOT EXISTS attempts_active_lease_idx
    ON task_engine.attempts (lease_expires_at)
    WHERE status IN ('claimed', 'running');

CREATE TABLE IF NOT EXISTS task_engine.progress (
    job_id UUID PRIMARY KEY REFERENCES task_engine.jobs(id) ON DELETE CASCADE,
    completed INTEGER NOT NULL CHECK (completed >= 0),
    total INTEGER CHECK (total >= 0),
    unit TEXT NOT NULL,
    revision BIGINT NOT NULL CHECK (revision >= 0),
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (total IS NULL OR completed <= total)
);

CREATE TABLE IF NOT EXISTS task_engine.events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES task_engine.jobs(id) ON DELETE CASCADE,
    attempt_id UUID,
    type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS events_job_order_idx
    ON task_engine.events (job_id, id);
