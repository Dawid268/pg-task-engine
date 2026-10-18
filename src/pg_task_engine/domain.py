"""Public immutable snapshots returned by the PostgreSQL queue engine."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum, unique
from uuid import UUID

from pg_task_engine.job_progress import JobProgress
from pg_task_engine.job_request import JSONPayload, JSONValue
from pg_task_engine.job_status import JobStatus
from pg_task_engine.task_ref import TaskRef


@unique
class AttemptStatus(StrEnum):
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    LOST = "lost"


@unique
class ErrorCode(StrEnum):
    EXECUTION_ERROR = "execution_error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"
    LEASE_LOST = "lease_lost"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    code: ErrorCode
    message: str
    exception_type: str | None = None


@dataclass(frozen=True, slots=True)
class JobResult:
    """An envelope distinguishing a successful JSON null from no result."""

    value: JSONValue


@dataclass(frozen=True, slots=True)
class EngineDefaults:
    """Execution policy used only when JobRequest leaves fields unspecified."""

    max_attempts: int = 3
    timeout: timedelta = timedelta(minutes=5)
    retry_delay: timedelta = timedelta(seconds=5)
    lease_duration: timedelta = timedelta(seconds=30)

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int:
            raise TypeError("max_attempts must be an integer")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        for name in ("timeout", "retry_delay", "lease_duration"):
            duration = getattr(self, name)
            if not isinstance(duration, timedelta):
                raise TypeError(f"{name} must be a timedelta")
            if duration <= timedelta(0):
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedPolicy:
    max_attempts: int
    timeout: timedelta
    retry_delay: timedelta


@dataclass(frozen=True, slots=True)
class JobSnapshot[QueueT: StrEnum]:
    id: UUID
    task: TaskRef
    queue: QueueT
    payload: JSONPayload
    status: JobStatus
    policy: ResolvedPolicy
    idempotency_key: str | None
    created_at: datetime
    scheduled_at: datetime
    available_at: datetime | None
    first_started_at: datetime | None
    finished_at: datetime | None
    attempts_count: int
    current_attempt_id: UUID | None
    result: JobResult | None
    progress: JobProgress | None
    cancel_requested: bool
    revision: int


@dataclass(frozen=True, slots=True)
class JobAttempt:
    id: UUID
    job_id: UUID
    number: int
    worker_id: UUID
    status: AttemptStatus
    claimed_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime
    lease_expires_at: datetime
    deadline_at: datetime | None
    finished_at: datetime | None
    execution_duration_ms: int | None
    error: ErrorInfo | None


@dataclass(frozen=True, slots=True)
class JobEvent:
    id: int
    job_id: UUID
    attempt_id: UUID | None
    type: str
    from_status: JobStatus | None
    to_status: JobStatus | None
    created_at: datetime
