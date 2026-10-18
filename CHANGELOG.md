# Changelog

## 0.1.0a2 (release-hardening candidate; not yet published)

- Forward-only, checksummed migrations with 001 legacy metadata upgrade,
  unknown-future-version detection, and a deadline recovery index.
- Independent-process PostgreSQL contention test.
- Complete distribution metadata and a deliberate, operator-approved PyPI
  release workflow with trusted publishing.
- Wheel installation verification in isolated environments.

## 0.1.0a1 (local alpha; not published)

- Typed and validated `TaskRef`, `JobStatus`, `JobRequest`,
  `ExecutionPolicy` and `JobProgress` contracts.
- PostgreSQL 16+ storage with explicit versioned SQL migration.
- Transactional enqueue, idempotency fingerprint, token-fenced claim/start,
  heartbeat, retries, deadline/lost-attempt recovery and terminal result.
- Concurrent `FOR UPDATE SKIP LOCKED` claims with separate attempt/event history.
- Versioned task registration, optional input/output validators,
  synchronous/asynchronous callbacks, progress and cooperative cancellation.
- Public SDK exports, operational CLI, local quickstart, and CI tests
  using a real PostgreSQL service.
- All features are pre-release and must not be treated as a production
  readiness/security guarantee.
