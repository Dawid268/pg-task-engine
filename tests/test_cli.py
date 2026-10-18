"""Simple CLI smoke tests that do not need a running PostgreSQL server."""

from pathlib import Path

import pytest

from pg_task_engine.cli import _load_engine, main


def test_cli_help_explains_supported_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "migrate" in output
    assert "worker" in output
    assert "enqueue" in output
    assert "inspect" in output


def test_cli_rejects_missing_required_engine_factory() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["worker", "--queue", "emails"])
    assert exit_info.value.code == 2


def test_cli_rejects_missing_operator_app_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="directory"):
        _load_engine("examples.quickstart:build_engine", app_path=str(tmp_path / "missing"))
