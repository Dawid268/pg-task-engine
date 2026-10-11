# Foundation Implementation Plan

> Historical execution record of the initial packaging-only setup. The later correction to the `touchpoint-taxonomy` boilerplate adds a reference API, configuration and container templates. See `docs/learning/02-touchpoint-boilerplate.md` and README for the current state. The original three-test results below describe the earlier stage.

> For agentic workers: use superpowers:executing-plans for the bounded setup. Preserve the student's hands-on learning workflow; do not implement queue logic.

**Goal:** An independently installable Python package with verified development tooling.

**Architecture:** A src-layout library with no runtime dependencies. FastAPI and GCP remain later integrations. The current setup implements package metadata, not the queue.

**Tech Stack:** Python 3.13, uv 0.10.9, uv_build, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-09-foundation-design.md`

## Global constraints

- Work only inside this project directory.
- No runtime dependencies for the foundation.
- Minimum Python `>=3.13`; development baseline `3.13`.
- Do not start external services, deploy cloud resources or publish packages.
- Use dedicated file tools for source/configuration edits.

## Review focus

- Version drift: compare `__version__` with installed distribution metadata.
- Missing typing marker: read `py.typed` from installed package resources.
- Editable-install false positive: install the built wheel in an isolated environment and import there.
- Accidental runtime dependencies: inspect wheel metadata and assert no `Requires-Dist` entries.
- Misleading completion: explicitly report that queue, workers, API and database are not implemented.

## Task 1: Package foundation

**Files:** `pyproject.toml`, `.python-version`, `.gitignore`, `.editorconfig`, `src/pg_task_engine/__init__.py`, `src/pg_task_engine/py.typed`, `tests/test_package.py`, `docs/learning/01-start.md`, `README.md`; generated `uv.lock`.

**Interface:** `pg_task_engine.__version__: str` equals `0.0.1` and matches package metadata.

- [x] Write configuration and packaging tests before the package implementation.
- [x] Run the tests against the incomplete package and record the expected failures.
- [x] Add the minimal version export and typing marker.
- [x] Resolve and lock development dependencies with uv.
- [x] Run pytest, Ruff lint/format checks and strict mypy.
- [x] Build wheel and source distribution; verify a clean wheel installation.
- [x] Add Polish learning notes and report actual results and remaining work.

## Execution evidence

Python 3.13.12; uv 0.10.9. Before package creation, all three packaging tests failed because neither the module nor distribution metadata existed. After installation, all three passed. Ruff lint and formatting checks passed; strict mypy reported no issues in two source files. `uv build` produced a wheel and source distribution. An isolated wheel-only installation imported from its own site-packages, included `py.typed`, and had neither FastAPI nor SQLAlchemy installed. The same three tests passed against the wheel in a separate environment.

This is packaging verification only. No task engine, database schema, worker, HTTP API, CI workflow or cloud resources were implemented.

No commit or remote publication is part of this step. This local setup does not imply GitHub or PyPI publication.
