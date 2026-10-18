# Contributing to pg-task-engine

Thanks for considering a contribution. The library is an educational
open-source project; keep changes small, well typed, documented and tested.

1. Open an issue describing the problem and expected behavior for
   substantial API changes.
2. Develop on a feature branch based on `dev`; do not rewrite shared
   history or commit passwords, DSNs, payload secrets or private datasets.
3. Add a regression test before fixing a reported bug. Run `uv sync --locked`,
   `uv run --locked pytest -q`, Ruff checks, strict mypy and `uv build`.
4. PostgreSQL integration tests require a **disposable** `*_test` database.
   They truncate `task_engine.jobs`; never point them at production.
5. Submit a PR into `dev` with test results and a short description
   of behavior and compatibility consequences.

Published migration SQL files are immutable. Never edit an existing
numbered migration: add the next consecutive SQL version and an upgrade
test instead. See [operations](docs/OPERATIONS.md) and
[release checklist](docs/RELEASING.md).
