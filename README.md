# pg-task-engine

A PostgreSQL-backed durable task queue for Python — a learning and open-source portfolio project.

**Status: library packaging and a reference API scaffold only. Task queues, workers, database integration, job migrations and GCP deployment are not implemented.**

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

## Learning milestones

1. Packaging and adapted API boilerplate (current work).
2. A small typed job model, validation and state transitions, implemented together with tests.
3. Explicit PostgreSQL migrations and one enqueue/execute/result flow.
4. Concurrent workers, leases, retries, logs and failure tests.
5. A real public library API, reference application and GCP deployment.

PostgreSQL drivers, SQLAlchemy and Alembic will be introduced with the first actual database use case. Empty database abstractions and dummy queue endpoints are not added in advance.

Learning notes are in `docs/learning/`. Older foundation records in `docs/superpowers/` describe the initial packaging-only stage, not the current reference API.

## References

- https://docs.astral.sh/uv/concepts/projects/dependencies/
- https://docs.astral.sh/uv/configuration/build-backend/
- https://docs.astral.sh/ruff/formatter/
