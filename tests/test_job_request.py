from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pg_task_engine.job_request import ExecutionPolicy, JobRequest, JSONPayload
from pg_task_engine.task_ref import TaskRef


class AppQueue(StrEnum):
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
