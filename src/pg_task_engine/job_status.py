from enum import StrEnum, unique


@unique
class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    CANCELLED = "cancelled"


def can_transition(
    current: JobStatus,
    target: JobStatus,
) -> bool:
    allowed_transitions = {
        JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
        JobStatus.RUNNING: {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.SUCCEEDED: set(),
        JobStatus.FAILED: {JobStatus.RETRY_SCHEDULED, JobStatus.CANCELLED},
        JobStatus.RETRY_SCHEDULED: {JobStatus.RUNNING, JobStatus.CANCELLED},
        JobStatus.CANCELLED: set(),
    }

    if current not in allowed_transitions:
        raise ValueError(f"Invalid current job status: {current}")

    return target in allowed_transitions[current]
