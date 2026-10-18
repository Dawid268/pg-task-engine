from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from pg_task_engine.task_ref import TaskRef

type JSONScalar = bool | int | float | str | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONPayload = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Optional overrides; the engine will resolve default values later."""

    max_attempts: int | None = None
    timeout: timedelta | None = None
    retry_delay: timedelta | None = None


@dataclass(frozen=True, slots=True)
class JobRequest[QueueT: StrEnum]:
    """Typed intent to enqueue a task; runtime validation comes separately."""

    task: TaskRef
    queue: QueueT
    payload: JSONPayload = field(default_factory=dict)
    not_before: datetime | None = None
    execution_policy: ExecutionPolicy | None = None
    idempotency_key: str | None = None
