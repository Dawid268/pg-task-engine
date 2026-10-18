from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import cast

import pytest

from pg_task_engine.job_progress import JobProgress
from pg_task_engine.job_progress_errors import (
    JobProgressErrorCode,
    JobProgressTypeError,
    JobProgressValueError,
)


def test_job_progress_stores_values() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    progress = JobProgress(
        completed=4000,
        total=10000,
        unit="emails",
        revision=1,
        updated_at=timestamp,
    )

    assert progress.completed == 4000
    assert progress.total == 10000
    assert progress.unit == "emails"
    assert progress.revision == 1
    assert progress.updated_at == timestamp


def test_job_progress_rejects_postgresql_incompatible_unit() -> None:
    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=1,
            total=2,
            unit="files\x00invalid",
            revision=1,
            updated_at=datetime(2026, 10, 18, tzinfo=UTC),
        )
    assert error.value.code is JobProgressErrorCode.UNIT_CONTAINS_NUL


def test_job_progress_rejects_unencodable_unicode_unit() -> None:
    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=1,
            total=2,
            unit="bad" + chr(0xD800) + "unit",
            revision=1,
            updated_at=datetime(2026, 10, 18, tzinfo=UTC),
        )
    assert error.value.code.value == "unit_invalid_unicode"


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "code_value"),
    [
        ("completed", 2**31, "completed_out_of_range"),
        ("total", 2**31, "total_out_of_range"),
        ("revision", 2**63, "revision_out_of_range"),
    ],
)
def test_job_progress_rejects_values_outside_postgresql_storage(
    field_name: str, invalid_value: int, code_value: str
) -> None:
    timestamp = datetime(2026, 10, 18, tzinfo=UTC)
    completed: int = 0
    total: int | None = None
    revision: int = 1
    if field_name == "completed":
        completed = invalid_value
    elif field_name == "total":
        total = invalid_value
    else:
        revision = invalid_value
    with pytest.raises(JobProgressValueError) as error:
        JobProgress(completed, total, "tasks", revision, timestamp)
    assert error.value.code.value == code_value


def test_job_progress_accepts_database_integer_limits() -> None:
    progress = JobProgress(
        completed=2**31 - 1,
        total=2**31 - 1,
        unit="tasks",
        revision=2**63 - 1,
        updated_at=datetime(2026, 10, 18, tzinfo=UTC),
    )
    assert progress.completed == 2**31 - 1
    assert progress.revision == 2**63 - 1


@pytest.mark.parametrize(
    "non_integer_completed",
    [1.5, "two", None, True],
    ids=["float", "string", "none", "boolean"],
)
def test_job_progress_rejects_non_integer_completed(
    non_integer_completed: object,
) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressTypeError) as error:
        JobProgress(
            completed=cast("int", non_integer_completed),
            total=10000,
            unit="emails",
            revision=1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.COMPLETED_NOT_INTEGER
    assert isinstance(error.value, TypeError)
    assert str(error.value)


@pytest.mark.parametrize(
    "negative_completed",
    [-1],
    ids=["negative"],
)
def test_job_progress_rejects_negative_completed(negative_completed: int) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=negative_completed,
            total=10000,
            unit="emails",
            revision=1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.COMPLETED_NEGATIVE
    assert isinstance(error.value, ValueError)


def test_job_progress_rejects_negative_total() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=4000,
            total=-10000,
            unit="emails",
            revision=1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.TOTAL_NEGATIVE


@pytest.mark.parametrize(
    "non_integer_total",
    [True, 1.5, "100", False],
    ids=["true", "float", "string", "false"],
)
def test_job_progress_rejects_non_integer_total(non_integer_total: object) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressTypeError) as error:
        JobProgress(
            completed=0,
            total=cast("int | None", non_integer_total),
            unit="emails",
            revision=1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.TOTAL_NOT_INTEGER


def test_job_progress_accepts_unknown_total() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    progress = JobProgress(completed=0, total=None, unit="emails", revision=1, updated_at=timestamp)
    assert progress.total is None


@pytest.mark.parametrize(
    ("code", "expected_value"),
    [
        (JobProgressErrorCode.COMPLETED_NOT_INTEGER, "completed_not_integer"),
        (JobProgressErrorCode.COMPLETED_NEGATIVE, "completed_negative"),
        (JobProgressErrorCode.COMPLETED_EXCEEDS_TOTAL, "completed_exceeds_total"),
        (JobProgressErrorCode.TOTAL_NOT_INTEGER, "total_not_integer"),
        (JobProgressErrorCode.TOTAL_NEGATIVE, "total_negative"),
        (JobProgressErrorCode.REVISION_NEGATIVE, "revision_negative"),
        (
            JobProgressErrorCode.REVISION_NOT_INTEGER,
            "revision_not_integer",
        ),
        (JobProgressErrorCode.UNIT_TYPE_ERROR, "unit_type_error"),
        (JobProgressErrorCode.UNIT_EMPTY, "unit_empty"),
        (JobProgressErrorCode.UPDATED_AT_TYPE_ERROR, "updated_at_type_error"),
        (JobProgressErrorCode.UPDATED_AT_NAIVE, "updated_at_naive"),
        (JobProgressErrorCode.UPDATED_AT_NOT_UTC, "updated_at_not_utc"),
    ],
)
def test_job_progress_error_codes_are_stable(
    code: JobProgressErrorCode,
    expected_value: str,
) -> None:
    assert code.value == expected_value


def test_job_progress_rejects_completed_greater_than_total() -> None:
    completed = 101
    total = 100
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=completed,
            total=total,
            unit="emails",
            revision=1,
            updated_at=timestamp,
        )

    assert error.value.code is JobProgressErrorCode.COMPLETED_EXCEEDS_TOTAL


def test_job_progress_accepts_completed_when_total_is_unknown() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    progress = JobProgress(
        completed=101,
        total=None,
        unit="emails",
        revision=1,
        updated_at=timestamp,
    )
    assert progress.completed == 101


def test_job_progress_rejects_negative_revision() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit="emails",
            revision=-1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.REVISION_NEGATIVE


@pytest.mark.parametrize(
    "non_integer_revision",
    [1.5, "two", None, True],
    ids=["float", "string", "none", "boolean"],
)
def test_job_progress_rejects_non_integer_revision(non_integer_revision: object) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressTypeError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit="emails",
            revision=cast("int", non_integer_revision),
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.REVISION_NOT_INTEGER
    assert isinstance(error.value, TypeError)
    assert str(error.value)


@pytest.mark.parametrize(
    "empty_unit",
    ["", "   ", "\t"],
    ids=["empty", "spaces", "tab"],
)
def test_job_progress_rejects_blank_unit(
    empty_unit: str,
) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit=empty_unit,
            revision=1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.UNIT_EMPTY


@pytest.mark.parametrize(
    "invalid_unit",
    [1, True, 1.5, None],
    ids=["integer", "boolean", "float", "none"],
)
def test_job_progress_rejects_not_string_unit(
    invalid_unit: object,
) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)

    with pytest.raises(JobProgressTypeError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit=cast("str", invalid_unit),
            revision=1,
            updated_at=timestamp,
        )
    assert error.value.code is JobProgressErrorCode.UNIT_TYPE_ERROR


def test_job_progress_keeps_non_blank_unit_whitespace() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    progress = JobProgress(
        completed=0,
        total=100,
        unit=" emails ",
        revision=1,
        updated_at=timestamp,
    )

    assert progress.unit == " emails "


def test_job_progress_rejects_naive_updated_at() -> None:
    naive_timestamp = datetime(2026, 10, 15, 10, 0)

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit="emails",
            revision=1,
            updated_at=naive_timestamp,
        )
    assert error.value.code is JobProgressErrorCode.UPDATED_AT_NAIVE


@pytest.mark.parametrize(
    "utc_offset",
    [timedelta(hours=2), timedelta(hours=-5, minutes=-30)],
    ids=["positive-offset", "negative-offset"],
)
def test_job_progress_rejects_non_utc_updated_at(utc_offset: timedelta) -> None:
    non_utc_timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=timezone(utc_offset))

    with pytest.raises(JobProgressValueError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit="emails",
            revision=1,
            updated_at=non_utc_timestamp,
        )
    assert error.value.code is JobProgressErrorCode.UPDATED_AT_NOT_UTC


@pytest.mark.parametrize(
    "invalid_timestamp",
    [None, "2026-10-15T10:00:00Z", 123, 1.5, date(2026, 10, 15)],
    ids=["none", "string", "integer", "float", "date-only"],
)
def test_job_progress_rejects_non_datetime_updated_at(invalid_timestamp: object) -> None:
    with pytest.raises(JobProgressTypeError) as error:
        JobProgress(
            completed=0,
            total=100,
            unit="emails",
            revision=1,
            updated_at=cast("datetime", invalid_timestamp),
        )
    assert error.value.code is JobProgressErrorCode.UPDATED_AT_TYPE_ERROR


@pytest.mark.parametrize(
    "zero_offset_zone",
    [UTC, timezone(timedelta(0), name="GMT")],
    ids=["datetime-utc", "other-zero-offset-zone"],
)
def test_job_progress_accepts_aware_utc_updated_at(zero_offset_zone: tzinfo) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=zero_offset_zone)
    progress = JobProgress(
        completed=10,
        total=100,
        unit="emails",
        revision=1,
        updated_at=timestamp,
    )

    assert progress.updated_at is timestamp


@pytest.mark.parametrize(
    ("completed", "total", "revision"),
    [(0, 0, 0), (100, 100, 1), (101, None, 5)],
    ids=["zero-total-and-revision", "completed-equals-total", "unknown-total"],
)
def test_job_progress_accepts_boundary_values(
    completed: int, total: int | None, revision: int
) -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    progress = JobProgress(
        completed=completed,
        total=total,
        unit="emails",
        revision=revision,
        updated_at=timestamp,
    )

    assert (progress.completed, progress.total, progress.revision) == (
        completed,
        total,
        revision,
    )


def test_job_progress_is_frozen_and_uses_slots() -> None:
    progress = JobProgress(
        completed=2,
        total=10,
        unit="emails",
        revision=1,
        updated_at=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
    )

    attribute = "completed"
    with pytest.raises(FrozenInstanceError):
        setattr(progress, attribute, 9)
    assert not hasattr(progress, "__dict__")


def test_job_progress_equality_and_hashing_use_field_values() -> None:
    timestamp = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    first = JobProgress(2, 10, "emails", 1, timestamp)
    same_values = JobProgress(2, 10, "emails", 1, timestamp)
    different_revision = JobProgress(2, 10, "emails", 2, timestamp)

    assert first == same_values
    assert hash(first) == hash(same_values)
    assert first != different_revision
    assert len({first, same_values, different_revision}) == 2
