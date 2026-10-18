"""Real PostgreSQL integration tests against a dedicated disposable *_test DB.

Run with PG_TASK_ENGINE_TEST_DSN set.  Nothing is deleted in an arbitrary DB.
"""

import hashlib
import os
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import timedelta
from enum import StrEnum
from importlib.resources import files
from multiprocessing import get_context
from typing import cast
from uuid import uuid4

import psycopg
import pytest

from pg_task_engine.domain import AttemptStatus, EngineDefaults
from pg_task_engine.engine import (
    IdempotencyConflictError,
    InvalidTransitionError,
    StaleAttemptError,
    TaskEngine,
    TaskEngineError,
    UnknownTaskError,
)
from pg_task_engine.job_progress import JobProgress
from pg_task_engine.job_request import ExecutionPolicy, JobRequest, JSONPayload, JSONValue
from pg_task_engine.job_status import JobStatus
from pg_task_engine.task_ref import TaskRef
from pg_task_engine.worker import Worker

pytestmark = pytest.mark.postgres


class Queue(StrEnum):
    EMAILS = "emails"
    REPORTS = "reports"


SEND = TaskRef("send_email", 1)
REPORT = TaskRef("generate_report", 2)


@pytest.fixture
def engine() -> Iterator[TaskEngine[Queue]]:
    dsn = os.environ.get("PG_TASK_ENGINE_TEST_DSN")
    if not dsn:
        pytest.skip("Set PG_TASK_ENGINE_TEST_DSN to a disposable PostgreSQL *_test database")
    with psycopg.connect(dsn) as conn:
        database = conn.execute("SELECT current_database()").fetchone()
        assert database is not None
        if not str(database[0]).endswith("_test"):
            pytest.fail("Refusing destructive database tests outside a *_test database")

    service = TaskEngine(
        dsn,
        queue_enum=Queue,
        default_queue=Queue.EMAILS,
        defaults=EngineDefaults(
            max_attempts=3,
            timeout=timedelta(minutes=2),
            retry_delay=timedelta(milliseconds=1),
            lease_duration=timedelta(seconds=30),
        ),
    )
    service.migrate()
    service.migrate()
    with psycopg.connect(dsn) as conn:
        conn.execute("TRUNCATE task_engine.jobs CASCADE")
    service.register(SEND)
    service.register(REPORT)
    try:
        yield service
    finally:
        service.close()


def _request(
    task: TaskRef = SEND, *, queue: Queue = Queue.EMAILS, key: str | None = None
) -> JobRequest[Queue]:
    return JobRequest(
        task=task,
        queue=queue,
        payload={"recipient": "person@example.test", "settings": {"retry": True}},
        idempotency_key=key,
    )


def _claim_from_separate_process(dsn: str) -> str | None:
    """Each spawned process owns an independent PostgreSQL connection pool."""
    with TaskEngine(
        dsn,
        queue_enum=Queue,
        default_queue=Queue.EMAILS,
        pool_size=2,
    ) as engine:
        claim = engine.claim(Queue.EMAILS, worker_id=uuid4())
        return str(claim.job_id) if claim is not None else None


def test_migrations_record_checksums_for_all_bundled_versions(
    engine: TaskEngine[Queue],
) -> None:
    with psycopg.connect(engine.dsn) as conn:
        rows = conn.execute(
            "SELECT version, checksum FROM task_engine.schema_migrations ORDER BY version"
        ).fetchall()
        index_present = conn.execute(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'task_engine' AND indexname = 'attempts_deadline_active_idx'"
        ).fetchone()

    assert [version for version, _checksum in rows] == [1, 2]
    for version, checksum in rows:
        asset = next(
            path
            for path in files("pg_task_engine").joinpath("migrations").iterdir()
            if path.name.startswith(f"{version:03d}_")
        )
        assert checksum == hashlib.sha256(asset.read_bytes()).hexdigest()
    assert index_present is not None

    engine.migrate()
    with psycopg.connect(engine.dsn) as conn:
        reread = conn.execute(
            "SELECT version, checksum FROM task_engine.schema_migrations ORDER BY version"
        ).fetchall()
    assert reread == rows


def test_migrate_rejects_changed_applied_sql(engine: TaskEngine[Queue]) -> None:
    with psycopg.connect(engine.dsn) as conn:
        original = conn.execute(
            "SELECT checksum FROM task_engine.schema_migrations WHERE version = 1"
        ).fetchone()
        assert original is not None
        conn.execute(
            "UPDATE task_engine.schema_migrations SET checksum = %s WHERE version = 1",
            ("0" * 64,),
        )
    try:
        with pytest.raises(TaskEngineError, match="checksum"):
            engine.migrate()
    finally:
        with psycopg.connect(engine.dsn) as conn:
            conn.execute(
                "UPDATE task_engine.schema_migrations SET checksum = %s WHERE version = 1",
                (original[0],),
            )


def test_migrate_refuses_unknown_newer_database_version(engine: TaskEngine[Queue]) -> None:
    future_version = 9999
    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "INSERT INTO task_engine.schema_migrations (version, checksum) VALUES (%s, %s)",
            (future_version, "f" * 64),
        )
    try:
        with pytest.raises(TaskEngineError, match=r"newer|unknown"):
            engine.migrate()
    finally:
        with psycopg.connect(engine.dsn) as conn:
            conn.execute(
                "DELETE FROM task_engine.schema_migrations WHERE version = %s",
                (future_version,),
            )


def test_migration_and_enqueue_roundtrip(engine: TaskEngine[Queue]) -> None:
    request = _request()
    created = engine.enqueue(request)
    reread = engine.get(created.id)

    assert reread.id == created.id
    assert reread.task == SEND
    assert reread.queue is Queue.EMAILS
    assert reread.payload == request.payload
    assert reread.status is JobStatus.QUEUED
    assert reread.attempts_count == 0
    assert reread.available_at == reread.scheduled_at
    assert reread.created_at.utcoffset() == timedelta(0)
    assert reread.current_attempt_id is None
    assert reread.result is None
    assert reread.progress is None
    assert engine.attempts(created.id) == []
    assert [event.type for event in engine.events(created.id)] == ["enqueued"]


def test_enqueue_rejects_unknown_task_and_wrong_queue(engine: TaskEngine[Queue]) -> None:
    with pytest.raises(UnknownTaskError):
        engine.enqueue(_request(TaskRef("unregistered", 1)))

    class OtherQueue(StrEnum):
        EMAILS = "emails"

    with pytest.raises(TypeError, match="queue"):
        engine.enqueue(
            JobRequest(
                task=SEND,
                queue=cast("Queue", OtherQueue.EMAILS),
                payload={},
            )
        )


def test_enqueue_task_helper_uses_registered_default_queue(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue_task(SEND, payload={"message": "hello"})
    assert job.queue is Queue.EMAILS
    assert job.payload == {"message": "hello"}


def test_registered_input_validator_rejects_bad_payload(engine: TaskEngine[Queue]) -> None:
    def require_recipient(payload: JSONPayload) -> None:
        if not isinstance(payload.get("recipient"), str):
            raise ValueError("recipient must be a string")

    engine.register(SEND, input_validator=require_recipient)
    with pytest.raises(ValueError, match="recipient"):
        engine.enqueue_task(SEND, payload={"recipient": 123})
    assert engine.enqueue_task(SEND, payload={"recipient": "valid@example.test"}).id


def test_worker_revalidates_payload_against_registered_task_version(
    engine: TaskEngine[Queue],
) -> None:
    job = engine.enqueue_task(SEND, payload={"recipient": 123})

    def reject_old_payload(payload: JSONPayload) -> None:
        if not isinstance(payload.get("recipient"), str):
            raise ValueError("schema invalid")

    engine.register(
        SEND,
        handler=lambda _context, _payload: {"should_not_execute": True},
        input_validator=reject_old_payload,
    )
    assert Worker(engine, queue=Queue.EMAILS).run_once()
    assert engine.get(job.id).status is JobStatus.FAILED


def test_registered_output_validator_rejects_worker_result(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())

    def validate_output(value: JSONValue) -> None:
        if not isinstance(value, dict) or "ok" not in value:
            raise ValueError("result schema invalid")

    engine.register(
        SEND,
        handler=lambda _context, _payload: {"invalid": True},
        output_validator=validate_output,
    )
    assert Worker(engine, queue=Queue.EMAILS).run_once()
    assert engine.get(job.id).status is JobStatus.FAILED
    assert engine.attempts(job.id)[0].error is not None


def test_idempotency_same_intent_and_conflict(engine: TaskEngine[Queue]) -> None:
    first = engine.enqueue(_request(key="welcome:42"))
    second = engine.enqueue(_request(key="welcome:42"))
    assert first.id == second.id
    assert len(engine.events(first.id)) == 1
    with pytest.raises(IdempotencyConflictError):
        engine.enqueue(
            JobRequest(
                task=SEND,
                queue=Queue.EMAILS,
                payload={"recipient": "other@example.test"},
                idempotency_key="welcome:42",
            )
        )


def test_idempotency_treats_unspecified_policy_forms_as_same_intent(
    engine: TaskEngine[Queue],
) -> None:
    first = engine.enqueue(
        JobRequest(
            task=SEND,
            queue=Queue.EMAILS,
            payload={"a": 1, "b": 2},
            idempotency_key="same:unspecified-policy",
        )
    )
    second = engine.enqueue(
        JobRequest(
            task=SEND,
            queue=Queue.EMAILS,
            payload={"b": 2, "a": 1},
            execution_policy=ExecutionPolicy(),
            idempotency_key="same:unspecified-policy",
        )
    )
    assert second.id == first.id


def test_concurrent_idempotency_has_one_persisted_job(engine: TaskEngine[Queue]) -> None:
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs = list(pool.map(lambda _index: engine.enqueue(_request(key="same:42")), range(10)))
    assert len({job.id for job in jobs}) == 1
    assert len(engine.events(jobs[0].id)) == 1


def test_enqueued_payload_is_isolated_from_mutable_request(engine: TaskEngine[Queue]) -> None:
    request = _request()
    request.payload["settings"] = {"retry": False}
    created = engine.enqueue(request)
    request.payload["settings"] = {"retry": True}
    assert engine.get(created.id).payload["settings"] == {"retry": False}


def test_scheduled_jobs_are_not_claimed_early(engine: TaskEngine[Queue]) -> None:
    with psycopg.connect(engine.dsn) as conn:
        later = conn.execute("SELECT clock_timestamp() + interval '3 hours'").fetchone()
    assert later is not None
    engine.enqueue(JobRequest(task=SEND, queue=Queue.EMAILS, not_before=later[0]))
    assert engine.claim(Queue.EMAILS, worker_id=uuid4()) is None


def test_claim_start_success_and_nullable_result(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    worker_id = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker_id)
    assert attempt is not None
    assert attempt.number == 1
    assert attempt.status is AttemptStatus.CLAIMED
    assert attempt.started_at is None
    assert attempt.deadline_at is None
    assert engine.claim(Queue.EMAILS, worker_id=uuid4()) is None

    started = engine.start(attempt.id, worker_id=worker_id)
    assert started.status is AttemptStatus.RUNNING
    assert started.started_at is not None
    assert started.deadline_at is not None
    assert engine.heartbeat(attempt.id, worker_id=worker_id) is not None

    completed = engine.succeed(attempt.id, worker_id=worker_id, result=None)
    assert completed.status is JobStatus.SUCCEEDED
    assert completed.result is not None
    assert completed.result.value is None
    assert completed.current_attempt_id is None
    assert completed.finished_at is not None
    assert engine.attempts(job.id)[0].status is AttemptStatus.SUCCEEDED
    assert engine.claim(Queue.EMAILS, worker_id=uuid4()) is None
    assert [event.type for event in engine.events(job.id)] == [
        "enqueued",
        "claimed",
        "started",
        "succeeded",
    ]


def test_claim_is_atomic_among_concurrent_workers(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(
                lambda _index: engine.claim(Queue.EMAILS, worker_id=uuid4()),
                range(12),
            )
        )
    claimed = [attempt for attempt in results if attempt is not None]
    assert len(claimed) == 1
    assert claimed[0].job_id == job.id
    assert engine.get(job.id).attempts_count == 1
    assert len(engine.attempts(job.id)) == 1


def test_claims_are_atomic_across_independent_processes(engine: TaskEngine[Queue]) -> None:
    jobs = [engine.enqueue(_request()) for _ in range(8)]
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as pool:
        result = list(pool.map(_claim_from_separate_process, [engine.dsn] * 8))
    assert len(result) == len(jobs)
    assert set(result) == {str(job.id) for job in jobs}
    for job in jobs:
        assert engine.get(job.id).attempts_count == 1
        assert len(engine.attempts(job.id)) == 1


def test_retry_and_exhaustion(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(
        JobRequest(
            task=SEND,
            queue=Queue.EMAILS,
            execution_policy=ExecutionPolicy(
                max_attempts=2,
                retry_delay=timedelta(milliseconds=1),
            ),
        )
    )
    token = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=token)
    assert attempt is not None
    engine.start(attempt.id, worker_id=token)
    waiting = engine.fail(attempt.id, worker_id=token, retryable=True, code="execution_error")
    assert waiting.status is JobStatus.RETRY_SCHEDULED
    assert waiting.attempts_count == 1
    assert waiting.available_at is not None
    assert waiting.finished_at is None
    with pytest.raises(StaleAttemptError):
        engine.succeed(attempt.id, worker_id=token, result="late")

    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "UPDATE task_engine.jobs SET available_at = clock_timestamp() - interval '1 second' "
            "WHERE id = %s",
            (job.id,),
        )
    second = engine.claim(Queue.EMAILS, worker_id=token)
    assert second is not None
    assert second.number == 2
    engine.start(second.id, worker_id=token)
    finished = engine.fail(second.id, worker_id=token, retryable=True)
    assert finished.status is JobStatus.FAILED
    assert finished.finished_at is not None
    assert finished.attempts_count == 2
    assert [attempt.status for attempt in engine.attempts(job.id)] == [
        AttemptStatus.FAILED,
        AttemptStatus.FAILED,
    ]
    assert engine.claim(Queue.EMAILS, worker_id=uuid4()) is None


def test_fail_requires_started_attempt(engine: TaskEngine[Queue]) -> None:
    engine.enqueue(_request())
    worker = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker)
    assert attempt is not None
    with pytest.raises(InvalidTransitionError):
        engine.fail(attempt.id, worker_id=worker, retryable=True)


def test_expired_deadline_is_timeout_not_lost(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    worker = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker)
    assert attempt is not None
    engine.start(attempt.id, worker_id=worker)
    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "UPDATE task_engine.attempts SET deadline_at = clock_timestamp() - "
            "interval '1 second' WHERE id = %s",
            (attempt.id,),
        )
    with pytest.raises(StaleAttemptError):
        engine.heartbeat(attempt.id, worker_id=worker)
    assert engine.reap_expired() == 1
    assert engine.attempts(job.id)[0].status is AttemptStatus.TIMED_OUT
    assert engine.get(job.id).status is JobStatus.RETRY_SCHEDULED


def test_expired_attempt_is_reaped_and_late_result_fenced(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    worker = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker)
    assert attempt is not None
    engine.start(attempt.id, worker_id=worker)
    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "UPDATE task_engine.attempts SET lease_expires_at = clock_timestamp() - "
            "interval '1 second' WHERE id = %s",
            (attempt.id,),
        )
    assert engine.reap_expired() == 1
    assert engine.get(job.id).status is JobStatus.RETRY_SCHEDULED
    assert engine.attempts(job.id)[0].status is AttemptStatus.LOST
    with pytest.raises(StaleAttemptError):
        engine.succeed(attempt.id, worker_id=worker, result={"unsafe": True})


def test_save_progress_requires_valid_token_and_new_revision(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    worker = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker)
    assert attempt is not None
    engine.start(attempt.id, worker_id=worker)
    saved = engine.save_progress(
        attempt.id,
        worker_id=worker,
        completed=2,
        total=5,
        unit="images",
        revision=1,
    )
    assert isinstance(saved, JobProgress)
    assert saved.completed == 2
    assert engine.get(job.id).progress == saved
    with pytest.raises(InvalidTransitionError):
        engine.save_progress(
            attempt.id,
            worker_id=worker,
            completed=3,
            total=5,
            unit="images",
            revision=1,
        )
    with pytest.raises(StaleAttemptError):
        engine.save_progress(
            attempt.id,
            worker_id=uuid4(),
            completed=3,
            total=5,
            unit="images",
            revision=2,
        )


def test_progress_survives_terminal_cancellation(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    worker = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker)
    assert attempt is not None
    engine.start(attempt.id, worker_id=worker)
    progress = engine.save_progress(
        attempt.id,
        worker_id=worker,
        completed=4,
        total=10,
        unit="files",
        revision=1,
    )
    engine.request_cancel(job.id)
    engine.confirm_cancel(attempt.id, worker_id=worker)
    finished = engine.get(job.id)
    assert finished.status is JobStatus.CANCELLED
    assert finished.progress == progress


def test_cancel_pending_and_running(engine: TaskEngine[Queue]) -> None:
    pending = engine.enqueue(_request())
    cancelled = engine.request_cancel(pending.id)
    assert cancelled.status is JobStatus.CANCELLED
    assert cancelled.finished_at is not None
    assert engine.claim(Queue.EMAILS, worker_id=uuid4()) is None

    running = engine.enqueue(_request())
    worker = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker)
    assert attempt is not None
    engine.start(attempt.id, worker_id=worker)
    requested = engine.request_cancel(running.id)
    assert requested.cancel_requested
    assert requested.status is JobStatus.RUNNING
    with pytest.raises(StaleAttemptError):
        engine.confirm_cancel(attempt.id, worker_id=uuid4())
    confirmed = engine.confirm_cancel(attempt.id, worker_id=worker)
    assert confirmed.status is JobStatus.CANCELLED
    assert confirmed.current_attempt_id is None
    with pytest.raises(StaleAttemptError):
        engine.succeed(attempt.id, worker_id=worker, result=None)


def test_cancellation_request_survives_lost_worker_and_does_not_execute_handler(
    engine: TaskEngine[Queue],
) -> None:
    job = engine.enqueue(_request())
    worker_id = uuid4()
    attempt = engine.claim(Queue.EMAILS, worker_id=worker_id)
    assert attempt is not None
    engine.start(attempt.id, worker_id=worker_id)
    assert engine.request_cancel(job.id).cancel_requested

    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "UPDATE task_engine.attempts SET lease_expires_at = "
            "clock_timestamp() - interval '1 second' WHERE id = %s",
            (attempt.id,),
        )
    assert engine.reap_expired() == 1
    waiting = engine.get(job.id)
    assert waiting.status is JobStatus.RETRY_SCHEDULED
    assert waiting.cancel_requested

    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "UPDATE task_engine.jobs SET available_at = clock_timestamp() - "
            "interval '1 second' WHERE id = %s",
            (job.id,),
        )

    invoked: list[bool] = []

    def handler(_context: object, _payload: JSONPayload) -> JSONValue:
        invoked.append(True)
        return None

    engine.register(SEND, handler)
    assert Worker(engine, queue=Queue.EMAILS).run_once()
    finished = engine.get(job.id)
    assert finished.status is JobStatus.CANCELLED
    assert finished.attempts_count == 2
    assert not invoked


def test_worker_executes_registered_handler(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    engine.register(SEND, lambda _context, payload: {"accepted": payload["recipient"]})
    worker = Worker(engine, worker_id=uuid4(), queue=Queue.EMAILS)
    assert worker.run_once() is True
    assert worker.run_once() is False
    finished = engine.get(job.id)
    assert finished.status is JobStatus.SUCCEEDED
    assert finished.result is not None
    assert finished.result.value == {"accepted": "person@example.test"}


def test_worker_captures_exception_without_leaking_message(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())

    def raise_secret_error(_context: object, _payload: object) -> None:
        raise RuntimeError("secret credential value")

    engine.register(SEND, raise_secret_error)
    worker = Worker(engine, worker_id=uuid4(), queue=Queue.EMAILS)
    assert worker.run_once() is True
    assert engine.get(job.id).status is JobStatus.RETRY_SCHEDULED
    assert "secret credential value" not in str(engine.attempts(job.id)[0])


def test_worker_accepts_async_handler(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())

    async def send_async(_context: object, payload: JSONPayload) -> JSONValue:
        return {"ack": payload["recipient"]}

    engine.register(SEND, send_async)
    assert Worker(engine, queue=Queue.EMAILS).run_once()
    finished = engine.get(job.id)
    assert finished.status is JobStatus.SUCCEEDED
    assert finished.result is not None
    assert finished.result.value == {"ack": "person@example.test"}


def test_worker_retries_and_succeeds_after_transient_failure(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    counter = 0

    def flaky(_context: object, _payload: JSONPayload) -> JSONValue:
        nonlocal counter
        counter += 1
        if counter == 1:
            raise RuntimeError("temporary failure")
        return {"attempts": counter}

    engine.register(SEND, flaky)
    worker = Worker(engine, queue=Queue.EMAILS)
    assert worker.run_once()
    assert engine.get(job.id).status is JobStatus.RETRY_SCHEDULED
    with psycopg.connect(engine.dsn) as conn:
        conn.execute(
            "UPDATE task_engine.jobs SET available_at = clock_timestamp() - interval '1 second' "
            "WHERE id = %s",
            (job.id,),
        )
    assert worker.run_once()
    assert engine.get(job.id).status is JobStatus.SUCCEEDED
    assert counter == 2


def test_invalid_result_fails_job_without_retry(engine: TaskEngine[Queue]) -> None:
    job = engine.enqueue(_request())
    engine.register(SEND, lambda _context, _payload: {1, 2, 3})
    assert Worker(engine, queue=Queue.EMAILS).run_once()
    finished = engine.get(job.id)
    assert finished.status is JobStatus.FAILED
    assert finished.result is None
    error = engine.attempts(job.id)[0].error
    assert error is not None
    assert error.code.value == "validation_error"
