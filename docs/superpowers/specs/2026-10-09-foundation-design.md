# Foundation: pg-task-engine

> Historical packaging-only specification. The user subsequently selected `/home/dawid/Projekty/touchpoint-taxonomy` as the boilerplate source. Current adaptations and exclusions are documented in `docs/learning/02-touchpoint-boilerplate.md`; that document and README supersede the original source selection and API deferral below.

## Intent and scope

Create a separate local Python library project for learning Python, FastAPI, PostgreSQL and later GCP. The requested first step is project setup, not autonomous implementation of the task engine. Use the existing komino-api toolchain as a reference, without copying or modifying its code or permissive type-checker settings.

## Initial decisions

- Working distribution name: `pg-task-engine`; import package: `pg_task_engine`. The name is not reserved on any registry.
- Python development baseline: `3.13`; minimum supported metadata: `>=3.13`.
- Source layout: `src/pg_task_engine/`; version: `0.0.1`.
- Build backend: `uv_build>=0.10.9,<0.11`, compatible with the installed uv 0.10.9. This is a deliberate tested baseline, not a claim to use the latest release.
- Zero runtime dependencies for this foundation. Add PostgreSQL and optional FastAPI dependencies with their first actual use case.
- Development tools: pytest, pytest-cov, Ruff formatting/linting, strict mypy. Store resolved versions in `uv.lock`.
- Library API at this stage: only `__version__: str`, plus a packaged `py.typed` marker.
- No imports that start workers, configure root logging, connect to a database or contact GCP.
- No queue functions, fake storage adapters or placeholder HTTP endpoints.
- No GitHub/PyPI publication, cloud resources, credentials or modifications to other projects.
- Document learning notes in Polish. Write implementation identifiers and public package documentation in English.

## Acceptance

The package builds as a wheel and source distribution. Tests check the import version against installed metadata and inclusion of `py.typed`. Lint, formatting and strict type checking pass. The wheel is independently installed and imported outside the development environment without installing FastAPI or PostgreSQL dependencies. These checks establish packaging only; they do not establish task-engine correctness.

## Following milestone (not implemented here)

Discuss and implement a small typed job model and its validation together. After that, introduce explicit state transitions and the first database-backed enqueue/execute/result path. Keep the library independent from the optional HTTP API and GCP deployment.

## Sources

- https://docs.astral.sh/uv/concepts/projects/init/#libraries
- https://docs.astral.sh/uv/configuration/build-backend/
