# pg-task-engine

A PostgreSQL-backed durable task queue for Python — a learning and open-source portfolio project.

**Status: library packaging, a reference API scaffold, and early domain models
(`TaskRef`, `JobStatus`, `JobProgress`). Durable task queues, workers, database
integration, job migrations and GCP deployment are not implemented.**

## Boilerplate source

The requested reference is **`/home/dawid/Projekty/touchpoint-taxonomy`**, not `komino-api`.

The application factory, `app/modules` layout, settings accessor, async HTTP testing approach, Ruff rule families, pre-commit tooling and container build structure are adapted from that project. This is not a clone: business models, existing migrations, credentials, corporate `mxmz-*` dependencies and company deployment configuration are intentionally excluded.

See `docs/learning/02-touchpoint-boilerplate.md` for the mapping and deliberate changes.

Project repository: https://github.com/Dawid268/pg-task-engine

`pg-task-engine` remains a working package name. No PyPI release or registry reservation has been made. An open-source license has not yet been selected.

## Two separate concerns

- `src/pg_task_engine/` is the installable library. Its foundation currently has no runtime dependencies. Importing it does not start an API, connect to a database or configure logging.
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
attempt/lease to prevent stale workers from overwriting progress. The persistence
and retry mechanisms are not implemented yet.

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
the future database-backed engine.

## Local setup

Python 3.13 is the development baseline; uv selects it without changing system Python.

```bash
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests run.py
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

The optional `database` profile defines an isolated PostgreSQL development service. It is **not used by the API yet**. Set your own nonempty `POSTGRES_PASSWORD` in an ignored local `.env` before explicitly starting it:

```bash
docker compose --profile database up -d db
```

Without a password, first initialization of this database should fail rather than enable passwordless access. No source-project database, tables, migrations or test data are reused. Default host port: `15439`.

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
2. A small typed job model, validation and state transitions (in progress; initial domain types implemented).
3. Explicit PostgreSQL migrations and one enqueue/execute/result flow.
4. Concurrent workers, leases, retries, logs and failure tests.
5. A real public library API, reference application and GCP deployment.

PostgreSQL drivers, SQLAlchemy and Alembic will be introduced with the first actual database use case. Empty database abstractions and dummy queue endpoints are not added in advance.

Learning notes are in `docs/learning/`. Older foundation records in `docs/superpowers/` describe the initial packaging-only stage, not the current reference API.

## References

- https://docs.astral.sh/uv/concepts/projects/dependencies/
- https://docs.astral.sh/uv/configuration/build-backend/
- https://docs.astral.sh/ruff/formatter/
