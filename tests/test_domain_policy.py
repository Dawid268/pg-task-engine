"""Limits whose persistent PostgreSQL representation is a 32-bit integer."""

from datetime import timedelta

import pytest

from pg_task_engine.domain import EngineDefaults


def test_engine_defaults_accept_postgresql_max_attempts_limit() -> None:
    policy = EngineDefaults(max_attempts=2**31 - 1)
    assert policy.max_attempts == 2**31 - 1


def test_engine_defaults_reject_attempts_outside_postgresql_integer() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        EngineDefaults(max_attempts=2**31)


def test_engine_defaults_still_accept_valid_positive_durations() -> None:
    defaults = EngineDefaults(
        max_attempts=1,
        timeout=timedelta(seconds=1),
        retry_delay=timedelta(milliseconds=1),
        lease_duration=timedelta(seconds=1),
    )
    assert defaults.max_attempts == 1


@pytest.mark.parametrize("invalid_days", [36_501, 999_999_999])
def test_engine_defaults_reject_timeout_over_maximum(invalid_days: int) -> None:
    with pytest.raises(ValueError, match="timeout"):
        EngineDefaults(timeout=timedelta(days=invalid_days))


def test_engine_defaults_reject_retry_delay_over_maximum() -> None:
    with pytest.raises(ValueError, match="retry_delay"):
        EngineDefaults(retry_delay=timedelta(days=36_501))


def test_engine_defaults_reject_lease_duration_over_maximum() -> None:
    with pytest.raises(ValueError, match="lease_duration"):
        EngineDefaults(lease_duration=timedelta(days=36_501))


def test_engine_defaults_accept_maximum_supported_duration() -> None:
    defaults = EngineDefaults(
        timeout=timedelta(days=36_500),
        retry_delay=timedelta(days=36_500),
        lease_duration=timedelta(days=36_500),
    )
    assert defaults.timeout == timedelta(days=36_500)
