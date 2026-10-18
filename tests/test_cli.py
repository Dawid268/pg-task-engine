"""Simple CLI smoke tests that do not need a running PostgreSQL server."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from pg_task_engine.cli import _encode_value, _load_engine, main


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


@pytest.mark.parametrize("locator", ["example", ":create", "example:", ""])
def test_cli_rejects_bad_factory_locator(locator: str) -> None:
    with pytest.raises(ValueError, match=r"factory|syntax"):
        _load_engine(locator)


def test_cli_rejects_missing_or_invalid_engine_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pg_task_engine.cli.importlib.import_module",
        lambda _name: SimpleNamespace(missing=None, bad=object),
    )

    with pytest.raises(ValueError, match="factory"):
        _load_engine("fake:missing")
    with pytest.raises(TypeError, match="TaskEngine"):
        _load_engine("fake:bad")


class _TestQueue(StrEnum):
    EMAILS = "emails"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_TestQueue.EMAILS, "emails"),
        (UUID(int=1), "00000000-0000-0000-0000-000000000001"),
        (datetime(2026, 10, 18, tzinfo=UTC), "2026-10-18T00:00:00+00:00"),
        (timedelta(seconds=2, milliseconds=500), 2.5),
    ],
)
def test_cli_encodes_public_snapshot_values(value: object, expected: object) -> None:
    assert _encode_value(value) == expected


def test_cli_rejects_unsupported_json_encoder_type() -> None:
    with pytest.raises(TypeError, match="Cannot encode"):
        _encode_value(object())
