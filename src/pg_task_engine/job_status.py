from collections.abc import Mapping
from enum import StrEnum, unique
from types import MappingProxyType
from typing import Final


@unique
class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: Final[Mapping[JobStatus, frozenset[JobStatus]]] = MappingProxyType(
    {
        JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
        JobStatus.RUNNING: frozenset(
            {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.RETRY_SCHEDULED,
            }
        ),
        JobStatus.SUCCEEDED: frozenset(),
        JobStatus.FAILED: frozenset(),
        JobStatus.RETRY_SCHEDULED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
        JobStatus.CANCELLED: frozenset(),
    }
)


def can_transition(
    current: JobStatus,
    target: JobStatus,
) -> bool:
    """Check whether the Job lifecycle allows this edge in principle.

    An allowed edge does not authorize a state change. In particular,
    RUNNING -> CANCELLED requires a safely stopped worker and a valid
    attempt/lease, verified by the future persistence layer.
    """
    if not isinstance(current, JobStatus):
        raise TypeError("current must be a JobStatus")
    if not isinstance(target, JobStatus):
        raise TypeError("target must be a JobStatus")

    return target in _ALLOWED_TRANSITIONS[current]
