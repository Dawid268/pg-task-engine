from datetime import UTC, datetime
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
