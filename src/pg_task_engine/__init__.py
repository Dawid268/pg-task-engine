"""Public SDK for the PostgreSQL-backed durable task queue.

Importing the package never connects to PostgreSQL or runs migrations.
"""

from typing import Final

from pg_task_engine.domain import (
    AttemptStatus,
    EngineDefaults,
    ErrorCode,
    ErrorInfo,
    JobAttempt,
    JobEvent,
    JobResult,
    JobSnapshot,
    ResolvedPolicy,
)
from pg_task_engine.engine import (
    IdempotencyConflictError,
    InvalidTransitionError,
    JobNotFoundError,
    MigrationError,
    StaleAttemptError,
    TaskEngine,
    TaskEngineError,
    UnknownTaskError,
)
from pg_task_engine.job_progress import JobProgress
from pg_task_engine.job_request import (
    ExecutionPolicy,
    JobRequest,
    JSONPayload,
    JSONScalar,
    JSONValue,
)
from pg_task_engine.job_status import JobStatus, can_transition
from pg_task_engine.task_ref import TaskRef
from pg_task_engine.worker import TaskContext, Worker

__version__: Final[str] = "0.1.0a3"

__all__ = (
    "AttemptStatus",
    "EngineDefaults",
    "ErrorCode",
    "ErrorInfo",
    "ExecutionPolicy",
    "IdempotencyConflictError",
    "InvalidTransitionError",
    "JSONPayload",
    "JSONScalar",
    "JSONValue",
    "JobAttempt",
    "JobEvent",
    "JobNotFoundError",
    "JobProgress",
    "JobRequest",
    "JobResult",
    "JobSnapshot",
    "JobStatus",
    "MigrationError",
    "ResolvedPolicy",
    "StaleAttemptError",
    "TaskContext",
    "TaskEngine",
    "TaskEngineError",
    "TaskRef",
    "UnknownTaskError",
    "Worker",
    "__version__",
    "can_transition",
)
