-- Help expiry recovery find workers that reached their execution deadline.
-- This is a forward-only, transactional migration; do not edit after release.

CREATE INDEX IF NOT EXISTS attempts_deadline_active_idx
    ON task_engine.attempts (deadline_at)
    WHERE status IN ('claimed', 'running') AND deadline_at IS NOT NULL;
