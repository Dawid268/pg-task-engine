import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import cast

from pg_task_engine.job_status import JobStatus
from pg_task_engine.task_ref import TaskRef

type JSONScalar = bool | int | float | str | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONPayload = dict[str, JSONValue]

_MAX_PAYLOAD_BYTES = 65_536
_MAX_IDEMPOTENCY_KEY_LENGTH = 128


def _validate_json_value(value: object, active: set[int]) -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not isfinite(value):
            raise ValueError("payload cannot contain NaN or infinity")
        return
    if type(value) is dict:
        _validate_json_mapping(value, active)
        return
    if type(value) is list:
        _validate_json_list(value, active)
        return
    raise TypeError("payload contains an unsupported JSON value type")


def _validate_json_mapping(value: Mapping[object, object], active: set[int]) -> None:
    identity = id(value)
    if identity in active:
        raise ValueError("payload must not contain reference cycles")
    active.add(identity)
    try:
        for key, nested in value.items():
            if type(key) is not str:
                raise TypeError("payload object keys must be strings")
            _validate_json_value(nested, active)
    finally:
        active.remove(identity)


def _validate_json_list(value: list[object], active: set[int]) -> None:
    identity = id(value)
    if identity in active:
        raise ValueError("payload must not contain reference cycles")
    active.add(identity)
    try:
        for nested in value:
            _validate_json_value(nested, active)
    finally:
        active.remove(identity)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Optional overrides; the engine will resolve default values later."""

    max_attempts: int | None = None
    timeout: timedelta | None = None
    retry_delay: timedelta | None = None

    def __post_init__(self) -> None:
        self._validate_max_attempts()
        self._validate_duration("timeout", self.timeout)
        self._validate_duration("retry_delay", self.retry_delay)

    def _validate_max_attempts(self) -> None:
        if self.max_attempts is None:
            return
        if type(self.max_attempts) is not int:
            raise TypeError("max_attempts must be an integer or None")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")

    @staticmethod
    def _validate_duration(field_name: str, duration: timedelta | None) -> None:
        if duration is None:
            return
        if not isinstance(duration, timedelta):
            raise TypeError(f"{field_name} must be a timedelta or None")
        if duration <= timedelta(0):
            raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True, slots=True)
class JobRequest[QueueT: StrEnum]:
    """Validated intent to enqueue a task, not a persisted Job."""

    task: TaskRef
    queue: QueueT
    payload: JSONPayload = field(default_factory=dict)
    not_before: datetime | None = None
    execution_policy: ExecutionPolicy | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        self._validate_task()
        self._validate_queue()
        self._validate_not_before()
        self._validate_execution_policy()
        self._validate_idempotency_key()
        self._validate_payload()

    def _validate_task(self) -> None:
        if not isinstance(self.task, TaskRef):
            raise TypeError("task must be a TaskRef")

    def _validate_queue(self) -> None:
        if not isinstance(self.queue, StrEnum) or isinstance(self.queue, JobStatus):
            raise TypeError("queue must be an application-defined StrEnum")

    def _validate_not_before(self) -> None:
        if self.not_before is None:
            return
        if not isinstance(self.not_before, datetime):
            raise TypeError("not_before must be a datetime or None")
        offset = self.not_before.utcoffset()
        if offset is None or offset != timedelta(0):
            raise ValueError("not_before must be timezone-aware in UTC")

    def _validate_execution_policy(self) -> None:
        if self.execution_policy is not None and not isinstance(
            self.execution_policy, ExecutionPolicy
        ):
            raise TypeError("execution_policy must be an ExecutionPolicy or None")

    def _validate_idempotency_key(self) -> None:
        if self.idempotency_key is None:
            return
        if type(self.idempotency_key) is not str:
            raise TypeError("idempotency_key must be a string or None")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank")
        if len(self.idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency_key must have at most 128 characters")

    def _validate_payload(self) -> None:
        """Validate and copy strict JSON, measured as compact sorted-key UTF-8.

        The encoder writes non-ASCII characters directly and uses no optional
        whitespace. The resulting byte count is the 64 KiB limit.
        """
        if type(self.payload) is not dict:
            raise TypeError("payload must be a JSON object")
        try:
            _validate_json_value(self.payload, set())
        except RecursionError as error:
            raise ValueError("payload nesting is too deep") from error
        try:
            serialized = json.dumps(
                self.payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as error:
            raise ValueError("payload cannot be serialized as valid UTF-8 JSON") from error
        if len(serialized) > _MAX_PAYLOAD_BYTES:
            raise ValueError("payload cannot exceed 65536 serialized UTF-8 bytes")

        # JSON round-trip copies nested lists and dictionaries. A frozen dataclass
        # does not itself prevent callers from mutating an original input dict.
        object.__setattr__(self, "payload", cast("JSONPayload", json.loads(serialized)))
