# Publishing pg-task-engine — release checklist

This document prepares the **installable Python library**, not the optional
FastAPI reference application. The current candidate is `0.1.0a3`.
Nothing in this document has published a PyPI distribution or deployed GCP
infrastructure. Public releases cannot be fully undone; do not reuse a
published version number.

## 1. Preconditions (release gate)

- [ ] Public API, security limitations and breaking changes reviewed by the maintainer.
- [ ] All tests pass against a **disposable PostgreSQL `*_test` database**.
- [ ] Local static checks pass and the matching GitHub Actions CI run is green.
- [ ] Version matches between `pyproject.toml`, `uv.lock` and
      `pg_task_engine.__version__`.
- [ ] Both wheel and sdist build successfully, include their numbered SQL
      migrations and pass installation smoke testing outside the source tree.
- [ ] A fresh test database can be migrated, run a task and be cleaned up safely.
- [ ] Existing migration 001 installations upgrade without loss of jobs.
- [ ] Public package name is confirmed available on PyPI **at publication time**.
      A 404 response from the PyPI metadata API is not a name reservation.
- [ ] Repo license, links, release notes and vulnerability reporting are reviewed.
- [ ] The `main` branch is updated **only after a reviewed release PR**.

For reproducible local verification:

```bash
uv sync --locked
export PG_TASK_ENGINE_TEST_DSN='postgresql://USER:TEST_PASSWORD@HOST:PORT/pg_task_engine_test'
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests examples run.py
uv build
uvx --from twine==7.0.0 twine check dist/*
uv export --no-dev --no-hashes --no-emit-project --output-file /tmp/pg-task-runtime.txt
uvx --from pip-audit==2.10.1 pip-audit --requirement /tmp/pg-task-runtime.txt
```

Never substitute your production database for the integration test database:
tests explicitly truncate the library's tables. Use secrets or environment
variables to provide real DSNs, not committed files.

## 2. Configure GitHub protection and PyPI trust (maintainer actions)

The project owner must explicitly configure these external services:

1. Create GitHub Environments named `testpypi` and `pypi`. Configure
   **required reviewers** for `pypi` and consider environment branch/tag
   restrictions. A protected environment provides a separate approval gate.
2. On [TestPyPI](https://test.pypi.org/) and [PyPI](https://pypi.org/),
   configure a **Trusted Publisher** using GitHub Actions OIDC. For a new
   project, use the pending publisher procedure; pending registration **does
   not reserve the package name**.
3. Configure repository owner `Dawid268`, repository `pg-task-engine`,
   workflow filename `release.yml`, and the matching GitHub environment
   (`testpypi` or `pypi`). No PyPI API token is required by the workflow.
4. Ensure the workflow exists on the repository's **default branch** before
   expecting GitHub's manual workflow UI to offer it.

Official instructions:

- https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- https://docs.pypi.org/trusted-publishers/adding-a-publisher/
- https://docs.pypi.org/trusted-publishers/using-a-publisher/

## 3. Review, freeze and tag exact package source

After a reviewed and green PR into `main`, use a **new, immutable annotated
tag** matching the version in `pyproject.toml` (example shown for this
unpublished candidate):

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.1.0a3 -m "pg-task-engine 0.1.0a3"
git push origin v0.1.0a3
```

**Do not execute these commands until you intend to publish this particular
commit.** This project uses `dev` for integration and leaves `main`
unchanged during ordinary development. A tag push does **not** trigger the
publication workflow automatically.

The earlier `v0.1.0a2` tag is deliberately immutable and **must not be
published**: the release audit found unhandled-task claims and incorrect
retry classification. Create a new reviewed version/tag for these fixes.

## 4. Manually publish the verified artifacts

In GitHub Actions choose **Publish verified Python distributions**, select
the immutable version **tag**, choose the registry and type the exact
confirmation string `PUBLISH`. The workflow:

1. Refuses a branch ref, non-version tags and confirmation mismatches.
2. Checks that the tag equals the package version.
3. Runs Ruff, strict mypy and the full integration suite with PostgreSQL,
   plus a vulnerability audit of locked runtime dependencies.
4. Builds the wheel/sdist, checks distribution metadata with Twine and
   verifies an independent wheel installation.
5. Uploads only those tested artifacts to the selected index using OIDC,
   subject to the selected GitHub Environment approval policy.

Publish to **TestPyPI** first if you want an additional public dry run.
TestPyPI and PyPI are separate indexes, and distribution names/versions
uploaded there may have different availability. Publishing to TestPyPI is
still an external, irreversible action for that index.

After publishing to PyPI, verify the project page, installation from the
public index in a fresh venv, console entry point, bundled SQL migrations,
and the dependency metadata. Record the final Git commit, artifact SHA-256
checksums, available provenance attestations, CI run URL and PyPI release URL
in release notes.

## 5. Explicit non-goals and limitations

The library has **at-least-once** semantics, not exactly-once effects.
Active cancellation is cooperative. PostgreSQL transactions cannot undo
effects in external services. There is no untrusted-code sandbox, per-tenant
authorization, HTTP gateway, automatic database rollback, or production
GCP deployment. These are not publication prerequisites for an honestly
described **alpha** release, but are blockers for claims of production
hardening or a universal 1.0 guarantee.

For a production service, separately verify backup/restore, PostgreSQL
privileges and TLS, sustained multi-process load, live schema upgrade locks,
monitoring, controlled worker shutdown, secret management and operational
incident response.
