"""Smoke tests for package installation, not for queue behavior."""

from importlib import import_module
from importlib.metadata import requires, version
from importlib.resources import files


def test_public_version_matches_installed_distribution() -> None:
    """An installed package exposes the same version as its distribution."""
    package = import_module("pg_task_engine")

    assert package.__version__ == version("pg-task-engine")


def test_installed_package_includes_typing_marker() -> None:
    """Downstream type checkers can recognize the package as typed."""
    assert files("pg_task_engine").joinpath("py.typed").is_file()


def test_foundation_has_no_runtime_dependencies() -> None:
    """Importing the foundation does not require FastAPI or a database driver."""
    assert not requires("pg-task-engine")
