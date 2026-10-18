# pg-task-engine

A PostgreSQL-backed durable task queue for Python 3.13, with a typed SDK,
real SQL migrations, cooperative workers and an optional reference FastAPI app.

**Status: pre-release candidate `0.1.0a2` (not yet published).**
The core enqueue/claim/execute/result
flow works with PostgreSQL 16+, including idempotency, leases, retries,
timeouts, progress, events and cooperative cancellation. It is **not** a
guarantee of exactly-once execution, a hardened multi-tenant service or a
production deployment. Neither PyPI publication nor GCP deployment has
been performed.

See [release instructions](docs/RELEASING.md) before publishing. The release
workflow is deliberately manual and uses PyPI Trusted Publishing; no API
tokens or production database credentials are stored in this repository.

## Architecture and development origin

The optional FastAPI reference application was adapted from a separate local
boilerplate. Its configuration and tooling informed the development setup,
but private business models, credentials, internal dependencies and deployment
configuration are **not** included in the package.
See `docs/learning/02-touchpoint-boilerplate.md` for the technical mapping.

Project repository: https://github.com/Dawid268/pg-task-engine

`pg-task-engine` remains a working package name. No PyPI release or registry reservation has been made.

## Two separate concerns

- `src/pg_task_engine/` is the installable library, depending on `psycopg`
  and `psycopg_pool`. Importing it does not start an API, connect to a
  database or apply migrations.
- `app/` is a repository-only reference FastAPI application, using the source boilerplate's layout. It is not shipped inside the library wheel.

The `api` dependency group contains reference-application dependencies. The `dev` group includes `api` plus testing and quality tools. These groups are not published as library runtime requirements.

## JobProgress domain contract

`JobProgress` (`pg_task_engine.job_progress`) is an immutable snapshot of task progress,
not a database record or a durable business checkpoint. It does not save data or resume
partially completed work on its own.

| Field | Contract |
| --- | --- |
| `completed` | Non-negative `int` (booleans are rejected). |
| `total` | Non-negative `int` or `None` when the total is unknown. If set, `completed <= total`; zero is valid. |
| `unit` | Non-blank `str`, such as `"emails"` or `"files"`. Surrounding whitespace is preserved. |
| `revision` | Non-negative `int` (starting at zero is allowed), describing the snapshot version. |
| `updated_at` | A timezone-aware `datetime` with UTC offset exactly zero. Naive datetimes and non-zero offsets are rejected; no automatic timezone conversion occurs. |

Validation raises `JobProgressTypeError` or `JobProgressValueError` with a stable
`JobProgressErrorCode` in the exception's `.code` property. Consumers must not
depend on the wording of error messages.

The `frozen=True, slots=True` dataclass provides value-based equality and hashing.
An individual snapshot only validates that `revision >= 0`; it **cannot** decide
whether a write is newer than the state currently stored in PostgreSQL. Future
storage operations must atomically compare revisions and verify the active job
attempt/lease to prevent stale workers from overwriting progress. The
PostgreSQL engine now persists progress through `save_progress` and rejects
stale tokens or non-increasing revisions; this standalone model still does
not persist itself.

## JobStatus lifecycle contract

`JobStatus` (`pg_task_engine.job_status`) is a six-value `StrEnum` describing
the state of an entire Job, **not** a single `JobAttempt`.
`can_transition(current: JobStatus, target: JobStatus) -> bool` checks whether
a status change is permitted *in principle*:

| Current Job status | Allowed target statuses |
| --- | --- |
| `QUEUED` | `RUNNING`, `CANCELLED` |
| `RUNNING` | `SUCCEEDED`, `FAILED`, `RETRY_SCHEDULED`, conditionally `CANCELLED` |
| `RETRY_SCHEDULED` | `RUNNING`, `CANCELLED` |
| `SUCCEEDED`, `FAILED`, `CANCELLED` | None: these are terminal statuses |

`FAILED` means the **Job** has ended, not merely that one attempt failed.
When the retry policy allows another attempt, the transition is
`RUNNING -> RETRY_SCHEDULED`. Manually retrying a terminal Job requires a
**new Job with a new ID**. A status cannot transition to itself.

`RUNNING -> CANCELLED` is only a *conditional* edge: the future engine must
first confirm that the active worker has stopped safely, validate the current
attempt/lease, and atomically persist the cancellation. Requesting
cancellation alone does not change the Job status or undo external side
effects. The most recently committed `JobProgress` remains observable.

`can_transition` performs no I/O, does not mutate a Job, and does not validate
retry policies or cancellation prerequisites. It returns `False` for forbidden
edges between valid statuses and raises `TypeError` for non-`JobStatus`
arguments, **including raw strings** even though `StrEnum` compares equal
to strings with the same value. Durable transition enforcement belongs to
the database-backed engine and includes attempt/lease verification.

## JobRequest and execution policy

`JobRequest[QueueT]` (`pg_task_engine.job_request`) describes intent to enqueue
a task. The application supplies a `StrEnum` for queue names; ordinary strings
and `JobStatus` members are rejected. `TaskEngine` additionally verifies
that the queue member belongs to the application's registered queue enum.

```python
from datetime import timedelta
from enum import StrEnum

from pg_task_engine.job_request import ExecutionPolicy, JobRequest
from pg_task_engine.task_ref import TaskRef


class AppQueue(StrEnum):
    EMAILS = "emails"


request: JobRequest[AppQueue] = JobRequest(
    task=TaskRef("send_email", 1),
    queue=AppQueue.EMAILS,
    payload={"recipient_id": 42, "tags": ["welcome"]},
    execution_policy=ExecutionPolicy(
        max_attempts=3,
        timeout=timedelta(seconds=30),
        retry_delay=timedelta(seconds=5),
    ),
    idempotency_key="welcome-email:42",
)
```

`JobRequest` validates task and policy types, UTC-aware `not_before`,
nonblank idempotency keys up to 128 characters, and a strict JSON **object**
payload. The latter accepts nested dictionaries with string keys, lists,
strings, booleans, integers, finite floats and `None`; it rejects unsupported
objects, cycles, invalid Unicode and non-finite numbers. Serialization for the
64 KiB limit uses UTF-8 with sorted keys, no optional whitespace and literal
non-ASCII characters (`sort_keys=True`, `separators=(",", ":")`,
`ensure_ascii=False`). A JSON round-trip copies the input, including nested
objects. The stored `payload` remains a mutable dictionary; `frozen=True`
does not freeze nested containers. Treat it as a snapshot before enqueue.

`ExecutionPolicy` accepts optional overrides for `max_attempts >= 1`,
positive `timedelta` timeout and positive `timedelta` retry delay.
Unspecified values are resolved by `EngineDefaults` during enqueue. Neither
`JobRequest` nor `ExecutionPolicy` accesses PostgreSQL or executes tasks.

## Quickstart: persisted task execution

The repository contains `examples/quickstart.py`, including a trusted engine
factory and a registered `send_email` handler (it does **not** send real email).
Supply your own local password through an ignored `.env` file; never commit
a live database DSN or other credentials.

```bash
docker compose --profile database up -d db
export TASK_ENGINE_DSN='postgresql://task_engine:YOUR_LOCAL_PASSWORD@127.0.0.1:15439/pg_task_engine'
uv sync --locked
uv run --locked pg-task-engine migrate
uv run --locked python -m examples.quickstart
```

Alternatively, use the CLI to start a worker, enqueue a task and inspect its
UUID. Separate worker and enqueue processes must use the same trusted
`module:factory` configuration and PostgreSQL database.

```bash
uv run --locked pg-task-engine worker --app examples.quickstart:build_engine --app-path . --queue emails
uv run --locked pg-task-engine enqueue --app examples.quickstart:build_engine --app-path . --task send_email --version 1 --payload '{"recipient":"demo@example.test"}'
uv run --locked pg-task-engine inspect --app examples.quickstart:build_engine --app-path . --job-id JOB_UUID
```

`--app` names trusted Python code selected by the operator, and
`--app-path` explicitly adds its source root when that app is not installed
into the Python environment. Job payloads
cannot choose modules, Python callables or arbitrary HTTP URLs. The engine
stores its tables in the PostgreSQL schema `task_engine`. Database DDL runs
**only** when `migrate()` or the CLI migration command is invoked.

`enqueue` guarantees idempotency within one database installation when the
optional key matches the normalized intent, and rejects conflicting reuse.
`claim` uses `FOR UPDATE SKIP LOCKED` to assign an attempt and lease. Worker
callbacks run **outside** database transactions, with automatic heartbeat
and attempt fencing on completion. Their input and output can have optional
version-specific validators registered with `TaskRef`.

Default policy: 3 attempts, 5-minute execution deadline, 5-second retry
delay, 30-second lease. Customize it with `EngineDefaults` and
`ExecutionPolicy`. Jobs are **at-least-once**, not exactly-once:
external effects must use their own idempotency/fencing. Cancellation is
cooperative; the engine cannot forcibly stop arbitrary application code.
See [operations and safety](docs/OPERATIONS.md) for recovery and deployment
assumptions.

## Local setup

Python 3.13 is the development baseline; uv selects it without changing system Python.

```bash
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests examples run.py
uv build
```

## Run the reference API

```bash
uv run --locked python run.py
```

Local default: `http://127.0.0.1:9031`. `HOST`, `PORT`, `LOG_LEVEL` and `RELOAD` can be passed as process environment variables. Reload is disabled by default.

- `GET /version`: the installed library version as a JSON string.
- `GET /health/live`: `{"status":"alive"}`. This reports HTTP liveness, not worker or database readiness.
- `/docs`: generated API documentation.

No job-management endpoints or authentication system exist yet. Do not treat this as the completed task engine.

`Settings` reads `.env` or the file selected with `SETTINGS_ENV`. `.env.example` contains only non-secret example configuration. No `.env` file was copied from the source repository. CORS is disabled unless explicit origins are configured.

## Containers

```bash
docker compose --env-file .env.example config --quiet
docker compose up --build api
```

The API runs as a non-root user, respects `PORT`, and is published on loopback only in local Compose. The image build uses the lockfile and the `api` dependency group; it does not install development tools.

The optional `database` profile defines an isolated PostgreSQL development service. The reference API itself still only exposes health/version routes; library clients and workers can use that PostgreSQL instance. Set your own nonempty `POSTGRES_PASSWORD` in an ignored local `.env` before explicitly starting it:

```bash
docker compose --profile database up -d db
```

Without a password, first initialization should fail rather than enable
passwordless access. The database role is `task_engine`; PostgreSQL reserves
user and schema names beginning with `pg_`. No other projects' databases
are reused. Default host port: `15439`.

## Quality hooks

`.pre-commit-config.yaml` follows the source toolchain but runs the versions locked by this project. Its configuration can be checked with:

```bash
uv run --locked pre-commit validate-config
```

Git hooks are not installed automatically. To enable them in a local checkout, run `uv run --locked pre-commit install`. No corporate GitLab pipeline or cloud configuration has been copied.

## Guided learning

See [the Python and GCP learning agreement](docs/learning/00-course.md) (Polish).
Development proceeds through small, explained exercises, knowledge checks and verified commits.
The learner writes the domain code; agents do not build later milestones without an explicit request.
Repository instructions are in `AGENTS.md`.

## Learning milestones

1. Packaging and adapted API boilerplate (completed).
2. Typed request, progress and lifecycle models (completed).
3. Explicit PostgreSQL migrations and enqueue/execute/result (local alpha).
4. Concurrent claims, leases, retries, progress, events and failure tests (local alpha).
5. Production hardening, multi-process load testing, optional gateway and GCP deployment (not done).

The core uses `psycopg`, connection pooling and explicit SQL migration files.
SQLAlchemy and Alembic are not required. The reference FastAPI app remains a
separate application and is not included in the installable wheel.

Learning notes are in `docs/learning/`. Older foundation records in `docs/superpowers/` describe the initial packaging-only stage, not the current reference API.

## References

- https://docs.astral.sh/uv/concepts/projects/dependencies/
- https://docs.astral.sh/uv/configuration/build-backend/
- https://docs.astral.sh/ruff/formatter/
