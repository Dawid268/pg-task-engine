"""Smoke tests for package installation, not for queue behavior."""

from importlib import import_module
from importlib.metadata import requires, version
from importlib.resources import files
from pathlib import Path

import pg_task_engine


def test_package_exports_public_sdk() -> None:
    expected = (
        "AttemptStatus",
        "EngineDefaults",
        "ExecutionPolicy",
        "JobProgress",
        "JobRequest",
        "JobStatus",
        "MigrationError",
        "TaskEngine",
        "TaskRef",
        "Worker",
    )
    assert all(getattr(pg_task_engine, name, None) is not None for name in expected)


def test_wheel_migration_is_packaged() -> None:
    assert files("pg_task_engine").joinpath("migrations/001_initial.sql").is_file()
    assert files("pg_task_engine").joinpath("migrations/002_deadline_recovery_index.sql").is_file()


def test_license_exists_in_project_source() -> None:
    assert (Path(__file__).resolve().parents[1] / "LICENSE").is_file()


def test_public_version_matches_installed_distribution() -> None:
    """An installed package exposes the same version as its distribution."""
    package = import_module("pg_task_engine")

    assert package.__version__ == version("pg-task-engine")


def test_installed_package_includes_typing_marker() -> None:
    """Downstream type checkers can recognize the package as typed."""
    assert files("pg_task_engine").joinpath("py.typed").is_file()


def test_library_requires_only_postgresql_runtime_dependencies() -> None:
    """The installable engine depends on psycopg, not the reference API."""
    dependencies = requires("pg-task-engine") or []
    assert any("psycopg" in dependency for dependency in dependencies)
    assert not any("fastapi" in dependency.lower() for dependency in dependencies)
