# pg-task-engine — operations, migrations and safety

## Supported first release

Python 3.13+ and PostgreSQL 16+; a single installation database with an
application-controlled enum of queues. Every process using the same database
must register the task name, version and matching handler/schema validators
that it is allowed to execute. The installable package does not depend on
FastAPI or GCP and does not start network listeners.

The built-in `Worker` restricts PostgreSQL claims to task names **and**
versions with handlers registered in that process. A task with no matching
worker stays queued, retains its attempt count and can run when an appropriate
worker registers later. Custom executors should likewise provide their
supported task set when calling `TaskEngine.claim`; omitting that filter
retains the low-level claim-any-task API.

The API has a **local alpha** contract; test it and review security controls
before using it with live data. The gateway, tenant authorization, quotas,
online schema upgrades and externally supplied handlers are not provided.

## Database setup

Set `POSTGRES_PASSWORD` in a local ignored `.env` and run:

```bash
docker compose --profile database up -d db
export TASK_ENGINE_DSN='postgresql://task_engine:YOUR_LOCAL_PASSWORD@127.0.0.1:15439/pg_task_engine'
uv run --locked pg-task-engine migrate
```

`migrate()` holds a PostgreSQL transaction-level advisory lock and applies
only previously unapplied, consecutively numbered bundled SQL migrations.
Each applied revision records the SHA-256 of the exact migration file.
If a recorded checksum differs, a migration version is missing, or the database
contains a newer/unknown revision, the engine raises `MigrationError` rather
than silently running against the wrong schema. Existing installations with
the original `001`-only metadata table are upgraded once by recording the
`001` checksum before applying `002`. Checksums do not retroactively prove
which SQL produced a legacy unchecksummed installation.

The first migration
creates `task_engine.jobs`, `task_engine.attempts`,
`task_engine.events`, `task_engine.progress` and the
`task_engine.schema_migrations` version table; `002` adds an index used for
deadline recovery. DDL is transactional and may require strong schema locks;
plan a maintenance window when migrating large live databases. Never change historical
migration files after publishing a version; introduce a new numbered file
instead. No destructive or automatic drop function is exposed.

The application database user must have permissions to create schema and
tables during initial migration. Production installations should separate
the privileged migration role from restricted writer/reader roles.

## Typical SDK lifecycle

1. An application creates `JobRequest` (or `engine.enqueue_task`) with a
   registered `TaskRef` and member of its registered `StrEnum` queue.
2. The engine validates/copies JSON and optional task schema, resolves
   execution policy, then inserts the Job and idempotency fingerprint in
   **one transaction**. Database commit is the durable acceptance point.
3. A worker atomically selects a due Job via `FOR UPDATE SKIP LOCKED`,
   creates one `CLAIMED` attempt and returns the lease token.
4. `start()` confirms execution, starts the deadline and writes the first
   start timestamp. The handler executes outside any database transaction.
5. Heartbeats extend the lease but **never the execution deadline**.
   A worker can write progress, result or failure only while its attempt ID,
   worker ID, lease and deadline remain valid.
6. On retryable failure and remaining attempts, the same Job becomes
   `RETRY_SCHEDULED` and a new attempt can be assigned after the delay.
   Exhaustion produces the irreversible terminal `FAILED` status.
7. `reap_expired()` fences abandoned lease holders, closes attempts as
   `LOST` or `TIMED_OUT`, and reschedules or fails the Job. The provided
   polling Worker runs reaping automatically; custom executors must call it.

The progress revision must increase; the most recent committed progress
survives retries, failure and cancellation. `JobResult` preserves the
distinction between no result and a successful JSON `null`. Event history
is transactional, append-only and queryable with `engine.events(job_id)`.

## Cancellation and execution deadlines

- `request_cancel` immediately cancels only waiting Jobs. For an active
  Job, it sets `cancel_requested` but keeps the status `RUNNING`.
- If an active attempt loses its lease after cancellation was requested,
  the request survives a retry. A replacement worker first confirms
  cancellation instead of invoking the task handler.
- Cooperative handlers can poll `context.cancellation_requested()` and
  stop safely. Only the valid worker may call `confirm_cancel`.
- The provided Worker confirms cancellation after a handler returns; if a
  handler does not cooperate, no hard termination is promised.
- Timeout starts **at execution start**, not when the attempt is claimed.
  PostgreSQL's clock decides lease expiry and deadline enforcement.
- Expired attempts are fenced from writing results even if external code is
  still running. This does **not** prevent that code from modifying an
  unrelated system; use downstream idempotency keys/fencing tokens.

## At-least-once semantics and idempotency

An acknowledged PostgreSQL transaction durably records a Job, but neither
the library nor its callback wrapper can guarantee that external work runs
exactly once. A process might call a remote API successfully, then crash
before confirming success. A later attempt may call that API again.
Use application-specific idempotency keys and suitable external side-effect
guards. The library's `idempotency_key` deduplicates submission intent
**within a single configured database**; it does not make handlers exactly-once.

`TaskRef` version changes must be managed explicitly. A task that was
accepted under version 1 must not silently execute version 2's handler.
User-provided functions are registered by trusted application code, never
resolved by importing names contained in a JSON payload.

## Monitoring and resource planning

Inspect Jobs using `engine.get(job_id)`, attempts via `engine.attempts`,
and events via `engine.events`. Watch the oldest `available_at` timestamp,
queue depth, `RETRY_SCHEDULED` counts, `LOST` and `TIMED_OUT` attempts,
and worker heartbeat failures. `Worker.run_forever` polls and reaps; it is
not an external process supervisor. Run it under a managed service with
restart policy and graceful SIGTERM handling.

Connection pools default to a maximum of 10 connections per engine. Across
multiple processes/containers, budget total pool connections against
PostgreSQL's `max_connections`. Start with a modest count and measure.
Keep database transactions short; never execute handlers inside a SQL
transaction or hold a row lock across a remote API call.

## Tests on real PostgreSQL

`tests/test_engine_postgres.py` uses real database transactions, concurrent
workers, an isolated application schema inside a dedicated test database, and direct
fault injection of expired lease timestamps. It will skip if the
`PG_TASK_ENGINE_TEST_DSN` environment variable is absent. Before cleaning
test tables it verifies the database name ends in `_test`. **Never** point
that variable to a production database: its tests truncate queue tables.

```bash
export PG_TASK_ENGINE_TEST_DSN='postgresql://task_engine:LOCAL_TEST_PASSWORD@127.0.0.1:15439/pg_task_engine_test'
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests examples run.py
uv build
```

GitHub Actions starts its own dedicated PostgreSQL service to execute the
same tests. The integration suite also includes atomic claim checks performed
by independent Python processes with separate pools. The packaging pipeline
installs the built wheel outside the source checkout. This checks current code
but does not replace sustained load testing,
cross-process failure injection, security review or production readiness.

See [release process](RELEASING.md) for the manual, tag-verified PyPI/TestPyPI
workflows and the independent operator approvals they require.

## Security boundaries

Treat task payloads/results and connection DSNs as sensitive. Store database
credentials in a secret manager or protected environment variables; do not
commit them, log full requests or expose a PostgreSQL port publicly.
The library does not expose an unauthenticated job-management web API.
The separate FastAPI scaffold provides health/version only.

`pg-task-engine worker --app module:factory` imports trusted operator-supplied
application code. Never accept `--app` from untrusted user input. Validation
failures and worker exceptions are persisted using typed error codes and a
generic message. Application schema validators should similarly avoid
storing secrets in error messages. Database backups, encryption, tenant
isolation, permission grants and retention policy remain the operator's
responsibility.

## Not included in this alpha

Explicit schema downgrade/reversal; distributed scheduling priorities or
DAGs; quotas and multi-tenancy; a hardened HTTP gateway; GCP provisioning;
external sandboxing for untrusted handlers; exactly-once effects; callback
kill/interrupt of arbitrary Python code; and an officially published PyPI
release. Do not market these as implemented.
