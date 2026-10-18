import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from enum import Enum, StrEnum
from typing import cast

import pytest

from pg_task_engine.job_request import ExecutionPolicy, JobRequest, JSONPayload, JSONValue
from pg_task_engine.job_status import JobStatus
from pg_task_engine.task_ref import TaskRef


class AppQueue(StrEnum):
    EMAILS = "emails"


class OtherEnum(Enum):
    EMAILS = "emails"


def test_job_request_stores_typed_fields() -> None:
    task = TaskRef(name="send_email", version=1)
    not_before = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    policy = ExecutionPolicy(
        max_attempts=3,
        timeout=timedelta(seconds=30),
        retry_delay=timedelta(minutes=1),
    )
    payload: JSONPayload = {"recipient_id": 42, "tags": ["welcome"]}

    request: JobRequest[AppQueue] = JobRequest(
        task=task,
        queue=AppQueue.EMAILS,
        payload=payload,
        not_before=not_before,
        execution_policy=policy,
        idempotency_key="email:42:welcome",
    )

    assert request.task == task
    assert request.queue is AppQueue.EMAILS
    assert request.payload == payload
    assert request.not_before == not_before
    assert request.execution_policy == policy
    assert request.idempotency_key == "email:42:welcome"


def test_job_request_defaults_to_separate_empty_payloads() -> None:
    task = TaskRef(name="send_email", version=1)
    first = JobRequest(task=task, queue=AppQueue.EMAILS)
    second = JobRequest(task=task, queue=AppQueue.EMAILS)

    assert first.payload == {}
    assert second.payload == {}
    assert first.payload is not second.payload
    assert first.not_before is None
    assert first.execution_policy is None
    assert first.idempotency_key is None


def test_execution_policy_defaults_are_unspecified() -> None:
    policy = ExecutionPolicy()

    assert policy.max_attempts is None
    assert policy.timeout is None
    assert policy.retry_delay is None


@pytest.mark.parametrize(
    "invalid_task",
    [None, "send_email", 12, AppQueue.EMAILS],
    ids=["none", "string", "integer", "enum"],
)
def test_job_request_rejects_invalid_task_type(invalid_task: object) -> None:
    with pytest.raises(TypeError, match="task"):
        JobRequest(task=cast("TaskRef", invalid_task), queue=AppQueue.EMAILS)


@pytest.mark.parametrize(
    "invalid_queue",
    ["emails", None, 123, True, OtherEnum.EMAILS, JobStatus.RUNNING],
    ids=["string", "none", "integer", "boolean", "non-string-enum", "job-status-enum"],
)
def test_job_request_rejects_invalid_queue_type(invalid_queue: object) -> None:
    with pytest.raises(TypeError, match="queue"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=cast("AppQueue", invalid_queue),
        )


@pytest.mark.parametrize(
    "invalid_date",
    ["2026-10-18", date(2026, 10, 18), 10, True],
    ids=["string", "date-only", "integer", "boolean"],
)
def test_job_request_rejects_invalid_not_before_type(invalid_date: object) -> None:
    with pytest.raises(TypeError, match="not_before"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            not_before=cast("datetime", invalid_date),
        )


@pytest.mark.parametrize(
    "invalid_date",
    [
        datetime(2026, 10, 18, 12, 0),
        datetime(2026, 10, 18, 12, 0, tzinfo=timezone(timedelta(hours=2))),
        datetime(2026, 10, 18, 12, 0, tzinfo=timezone(timedelta(hours=-5))),
    ],
    ids=["naive", "utc-plus-two", "utc-minus-five"],
)
def test_job_request_rejects_non_utc_not_before(invalid_date: datetime) -> None:
    with pytest.raises(ValueError, match="not_before"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            not_before=invalid_date,
        )


def test_job_request_accepts_zero_utc_offset_and_past_date() -> None:
    supplied = datetime(2020, 1, 1, tzinfo=timezone(timedelta(0), name="GMT"))
    request = JobRequest(
        task=TaskRef("send_email", 1),
        queue=AppQueue.EMAILS,
        not_before=supplied,
    )
    assert request.not_before is supplied


@pytest.mark.parametrize("invalid_policy", [True, "retry", 3, AppQueue.EMAILS])
def test_job_request_rejects_non_policy_type(invalid_policy: object) -> None:
    with pytest.raises(TypeError, match="execution_policy"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            execution_policy=cast("ExecutionPolicy", invalid_policy),
        )


@pytest.mark.parametrize(
    "invalid_key",
    ["", " ", "\t", "x" * 129],
    ids=["empty", "space", "tab", "too-long"],
)
def test_job_request_rejects_invalid_idempotency_key_value(invalid_key: str) -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            idempotency_key=invalid_key,
        )


@pytest.mark.parametrize("invalid_key", [12, False, 1.5, ["abc"]])
def test_job_request_rejects_invalid_idempotency_key_type(invalid_key: object) -> None:
    with pytest.raises(TypeError, match="idempotency_key"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            idempotency_key=cast("str", invalid_key),
        )


def test_job_request_preserves_valid_idempotency_key() -> None:
    key = " email:123 " + "x" * (128 - len(" email:123 "))
    request = JobRequest(
        task=TaskRef("send_email", 1),
        queue=AppQueue.EMAILS,
        idempotency_key=key,
    )
    assert request.idempotency_key == key


@pytest.mark.parametrize(
    "invalid_payload",
    [None, [], "message", True, 15, (1, 2)],
    ids=["none", "list", "string", "bool", "integer", "tuple"],
)
def test_job_request_rejects_non_object_payload(invalid_payload: object) -> None:
    with pytest.raises(TypeError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload=cast("JSONPayload", invalid_payload),
        )


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"number": float("nan")},
        {"number": float("inf")},
        {"number": float("-inf")},
    ],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_job_request_rejects_non_finite_numbers(invalid_payload: JSONPayload) -> None:
    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload=invalid_payload,
        )


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {1: "value"},
        {"nested": {42: "value"}},
        {"items": [("tuple",)]},
        {"items": [{1, 2}]},
        {"items": [object()]},
        {"items": [datetime(2026, 10, 18, tzinfo=UTC)]},
    ],
    ids=["non-string-top-key", "non-string-nested-key", "tuple", "set", "object", "datetime"],
)
def test_job_request_rejects_non_json_values(invalid_payload: object) -> None:
    with pytest.raises(TypeError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload=cast("JSONPayload", invalid_payload),
        )


def test_job_request_rejects_cyclic_payload() -> None:
    payload: JSONPayload = {}
    payload["self"] = payload

    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload=payload,
        )


def test_job_request_rejects_cyclic_list_in_payload() -> None:
    items: list[JSONValue] = []
    items.append(items)

    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload={"items": items},
        )


def test_job_request_rejects_excessively_deep_json() -> None:
    payload: JSONPayload = {}
    current: JSONPayload = payload
    for _ in range(1_500):
        nested: JSONPayload = {}
        current["nested"] = nested
        current = nested

    with pytest.raises(ValueError, match="payload nesting"):
        JobRequest(task=TaskRef("send_email", 1), queue=AppQueue.EMAILS, payload=payload)


def test_job_request_rejects_unserializable_large_integer() -> None:
    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload={"big_integer": 10**5_000},
        )


def test_job_request_rejects_invalid_unicode_surrogate() -> None:
    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload={"text": "\ud800"},
        )


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"message": "before\x00after"},
        {"invalid\x00key": "value"},
        {"nested": {"items": ["one", "\x00"]}},
    ],
    ids=["nul-in-string", "nul-in-object-key", "nul-in-nested-list"],
)
def test_job_request_rejects_postgresql_incompatible_nul(
    invalid_payload: JSONPayload,
) -> None:
    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload=invalid_payload,
        )


def test_job_request_rejects_nul_in_idempotency_key() -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            idempotency_key="request\x00id",
        )


def test_job_request_rejects_invalid_queue_value() -> None:
    class BadQueue(StrEnum):
        INVALID = "emails\x00bad"

    with pytest.raises(ValueError, match="queue"):
        JobRequest(task=TaskRef("send_email", 1), queue=BadQueue.INVALID)


def test_job_request_accepts_json_scalars_and_unicode() -> None:
    payload: JSONPayload = {
        "text": "Zażółć gęślą jaźń 🐢",
        "active": True,
        "items": [None, False, 0, -1, 2.5, "x", {"ok": True}],
        "nested": {"other": [1, 2]},
    }
    request = JobRequest(task=TaskRef("send_email", 1), queue=AppQueue.EMAILS, payload=payload)
    assert request.payload == payload


def test_job_request_accepts_exact_64_kib_serialized_payload() -> None:
    overhead = len(json.dumps({"data": ""}, separators=(",", ":"), ensure_ascii=False).encode())
    payload: JSONPayload = {"data": "x" * (65_536 - overhead)}
    request = JobRequest(task=TaskRef("send_email", 1), queue=AppQueue.EMAILS, payload=payload)
    assert request.payload == payload


def test_job_request_rejects_payload_one_byte_over_limit() -> None:
    overhead = len(json.dumps({"data": ""}, separators=(",", ":"), ensure_ascii=False).encode())
    payload: JSONPayload = {"data": "x" * (65_537 - overhead)}
    with pytest.raises(ValueError, match="payload"):
        JobRequest(task=TaskRef("send_email", 1), queue=AppQueue.EMAILS, payload=payload)


def test_job_request_enforces_limit_on_utf8_bytes_not_characters() -> None:
    with pytest.raises(ValueError, match="payload"):
        JobRequest(
            task=TaskRef("send_email", 1),
            queue=AppQueue.EMAILS,
            payload={"data": "🐢" * 17_000},
        )


def test_job_request_copies_nested_payload_before_storing_it() -> None:
    letters: list[JSONValue] = ["a"]
    details: JSONPayload = {"count": 1}
    payload: JSONPayload = {"nested": {"letters": letters, "details": details}}

    request = JobRequest(task=TaskRef("send_email", 1), queue=AppQueue.EMAILS, payload=payload)
    letters.append("b")
    details["count"] = 99
    payload["added"] = True

    assert request.payload == {"nested": {"letters": ["a"], "details": {"count": 1}}}
    assert request.payload is not payload


def test_job_request_dataclass_fields_are_frozen() -> None:
    request = JobRequest(task=TaskRef("send_email", 1), queue=AppQueue.EMAILS)
    attribute = "task"
    with pytest.raises(FrozenInstanceError):
        setattr(request, attribute, TaskRef("other", 1))


def _policy_with_duration(field_name: str, duration: timedelta) -> ExecutionPolicy:
    if field_name == "timeout":
        return ExecutionPolicy(timeout=duration)
    return ExecutionPolicy(retry_delay=duration)


@pytest.mark.parametrize(
    "invalid_attempts",
    [0, -1, -3],
    ids=["zero", "negative", "larger-negative"],
)
def test_execution_policy_rejects_non_positive_attempts(invalid_attempts: int) -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        ExecutionPolicy(max_attempts=invalid_attempts)


@pytest.mark.parametrize(
    "invalid_attempts",
    [True, False, "3", 3.0],
    ids=["true", "false", "string", "float"],
)
def test_execution_policy_rejects_non_int_attempts(invalid_attempts: object) -> None:
    with pytest.raises(TypeError, match="max_attempts"):
        ExecutionPolicy(max_attempts=cast("int", invalid_attempts))


@pytest.mark.parametrize(
    ("field_name", "invalid_duration"),
    [
        ("timeout", timedelta(0)),
        ("timeout", timedelta(seconds=-1)),
        ("retry_delay", timedelta(0)),
        ("retry_delay", timedelta(milliseconds=-1)),
    ],
)
def test_execution_policy_rejects_non_positive_durations(
    field_name: str, invalid_duration: timedelta
) -> None:
    with pytest.raises(ValueError, match=field_name):
        _policy_with_duration(field_name, invalid_duration)


@pytest.mark.parametrize("invalid_duration", [123, "30", True, 1.5])
@pytest.mark.parametrize("field_name", ["timeout", "retry_delay"])
def test_execution_policy_rejects_non_timedelta_durations(
    field_name: str, invalid_duration: object
) -> None:
    with pytest.raises(TypeError, match=field_name):
        _policy_with_duration(field_name, cast("timedelta", invalid_duration))


def test_execution_policy_accepts_positive_durations_and_one_attempt() -> None:
    policy = ExecutionPolicy(
        max_attempts=1,
        timeout=timedelta(milliseconds=1),
        retry_delay=timedelta(microseconds=1),
    )
    assert policy.max_attempts == 1
    assert policy.timeout == timedelta(milliseconds=1)
    assert policy.retry_delay == timedelta(microseconds=1)


def test_execution_policy_dataclass_fields_are_frozen() -> None:
    policy = ExecutionPolicy(max_attempts=3)
    attribute = "max_attempts"
    with pytest.raises(FrozenInstanceError):
        setattr(policy, attribute, 4)
