from typing import cast

import pytest

from pg_task_engine.job_status import JobStatus, can_transition

# The expected outcomes are written independently of the production transition
# mapping. Rows and columns use this explicitly fixed ordering.
_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.RETRY_SCHEDULED,
    JobStatus.CANCELLED,
)
_EXPECTED_MATRIX = (
    (False, True, False, False, False, True),  # QUEUED
    (False, False, True, True, True, True),  # RUNNING
    (False, False, False, False, False, False),  # SUCCEEDED
    (False, False, False, False, False, False),  # FAILED
    (False, True, False, False, False, True),  # RETRY_SCHEDULED
    (False, False, False, False, False, False),  # CANCELLED
)
_TRANSITION_CASES = tuple(
    (current, target, expected)
    for current, results in zip(_STATUSES, _EXPECTED_MATRIX, strict=True)
    for target, expected in zip(_STATUSES, results, strict=True)
)


@pytest.mark.parametrize(
    ("current_status", "target_status", "expected"),
    _TRANSITION_CASES,
    ids=[f"{current.value}-to-{target.value}" for current, target, _ in _TRANSITION_CASES],
)
def test_every_status_transition(
    current_status: JobStatus, target_status: JobStatus, expected: bool
) -> None:
    assert can_transition(current_status, target_status) is expected


@pytest.mark.parametrize("status", _STATUSES)
def test_status_cannot_transition_to_itself(status: JobStatus) -> None:
    assert can_transition(status, status) is False


@pytest.mark.parametrize("status", [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED])
@pytest.mark.parametrize("target", _STATUSES)
def test_terminal_statuses_have_no_outgoing_transitions(
    status: JobStatus, target: JobStatus
) -> None:
    assert can_transition(status, target) is False


@pytest.mark.parametrize(
    "invalid_status",
    ["queued", "running", "not-a-status", None, 42, True, 1.5, object()],
    ids=[
        "queued-string",
        "running-string",
        "invalid-string",
        "none",
        "integer",
        "bool",
        "float",
        "object",
    ],
)
@pytest.mark.parametrize("argument", ["current", "target"])
def test_invalid_job_status_arguments_raise_type_error(
    invalid_status: object, argument: str
) -> None:
    invalid = cast("JobStatus", invalid_status)
    if argument == "current":
        current, target = invalid, JobStatus.RUNNING
    else:
        current, target = JobStatus.QUEUED, invalid

    with pytest.raises(TypeError, match=argument):
        can_transition(current, target)


def test_job_status_enum_values_are_stable_and_unique() -> None:
    expected = [
        ("QUEUED", "queued"),
        ("RUNNING", "running"),
        ("SUCCEEDED", "succeeded"),
        ("FAILED", "failed"),
        ("RETRY_SCHEDULED", "retry_scheduled"),
        ("CANCELLED", "cancelled"),
    ]
    actual = [(status.name, status.value) for status in JobStatus]

    assert actual == expected
    assert len({status.value for status in JobStatus}) == len(JobStatus)
