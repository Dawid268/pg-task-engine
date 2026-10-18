"""Cooperative, at-least-once task execution outside database transactions."""

import asyncio
import inspect
import logging
from collections.abc import Awaitable
from datetime import timedelta
from enum import StrEnum
from threading import Event, Thread
from time import monotonic
from typing import cast
from uuid import UUID, uuid4

from pg_task_engine.domain import ErrorCode
from pg_task_engine.engine import StaleAttemptError, TaskEngine
from pg_task_engine.job_progress import JobProgress
from pg_task_engine.job_request import JSONPayload, JSONValue
from pg_task_engine.task_ref import TaskRef

_LOG = logging.getLogger(__name__)


class _SchemaRejected(Exception):
    """A task-specific JSON validator rejected an input or output."""


async def _await_handler_result(value: Awaitable[object]) -> object:
    return await value


class TaskContext[QueueT: StrEnum]:
    """Capabilities held by the current worker attempt, never by a task payload."""

    def __init__(
        self,
        engine: TaskEngine[QueueT],
        *,
        job_id: UUID,
        attempt_id: UUID,
        worker_id: UUID,
    ) -> None:
        self.engine = engine
        self.job_id = job_id
        self.attempt_id = attempt_id
        self.worker_id = worker_id

    def heartbeat(self) -> None:
        self.engine.heartbeat(self.attempt_id, worker_id=self.worker_id)

    def save_progress(
        self,
        *,
        completed: int,
        total: int | None,
        unit: str,
        revision: int,
    ) -> JobProgress:
        return self.engine.save_progress(
            self.attempt_id,
            worker_id=self.worker_id,
            completed=completed,
            total=total,
            unit=unit,
            revision=revision,
        )

    def cancellation_requested(self) -> bool:
        return self.engine.get(self.job_id).cancel_requested


class Worker[QueueT: StrEnum]:
    """Poll one queue and run previously registered Python handlers.

    A heartbeat thread extends the lease while a handler executes. Completion
    is still fenced by the attempt token, deadline and PostgreSQL clock.
    """

    def __init__(
        self,
        engine: TaskEngine[QueueT],
        *,
        queue: QueueT,
        worker_id: UUID | None = None,
        poll_interval: timedelta = timedelta(seconds=1),
    ) -> None:
        if type(queue) is not engine.queue_enum:
            raise TypeError("worker queue must belong to the engine queue enum")
        if worker_id is not None and not isinstance(worker_id, UUID):
            raise TypeError("worker_id must be a UUID or None")
        if not isinstance(poll_interval, timedelta) or poll_interval <= timedelta(0):
            raise ValueError("poll_interval must be a positive timedelta")
        self.engine = engine
        self.queue = queue
        self.worker_id = worker_id if worker_id is not None else uuid4()
        self.poll_interval = poll_interval

    def _heartbeat_loop(self, attempt_id: UUID, stop: Event) -> None:
        delay = max(self.engine.defaults.lease_duration.total_seconds() / 3, 0.01)
        while not stop.wait(delay):
            try:
                self.engine.heartbeat(attempt_id, worker_id=self.worker_id)
            except StaleAttemptError:
                return
            except Exception:  # noqa: BLE001 - heartbeat failures must not crash executing handlers
                # The supervising worker must still attempt a fenced commit;
                # missed heartbeats cannot authorize a stale write.
                _LOG.warning("Heartbeat failed for attempt %s", attempt_id)

    def _validate_input(self, task: TaskRef, payload: JSONPayload) -> None:
        try:
            self.engine.validate_input(task, payload)
        except (ValueError, TypeError) as error:
            raise _SchemaRejected from error

    def _validate_output(self, task: TaskRef, value: JSONValue) -> None:
        try:
            self.engine.validate_output(task, value)
        except (ValueError, TypeError) as error:
            raise _SchemaRejected from error

    def run_once(self) -> bool:
        """Claim and execute one available task. Return False when idle."""
        attempt = self.engine.claim(
            self.queue,
            worker_id=self.worker_id,
            supported_tasks=self.engine.runnable_tasks,
        )
        if attempt is None:
            return False

        try:
            self.engine.start(attempt.id, worker_id=self.worker_id)
        except StaleAttemptError:
            return True
        start = monotonic()
        stop = Event()
        thread = Thread(
            target=self._heartbeat_loop,
            args=(attempt.id, stop),
            name=f"pg-task-heartbeat-{attempt.id}",
            daemon=True,
        )
        thread.start()
        try:
            job = self.engine.get(attempt.job_id)
            if job.cancel_requested:
                self.engine.confirm_cancel(attempt.id, worker_id=self.worker_id)
                return True

            context = TaskContext(
                self.engine,
                job_id=job.id,
                attempt_id=attempt.id,
                worker_id=self.worker_id,
            )
            self._validate_input(job.task, job.payload)
            handler = self.engine.handler_for(job.task)
            value = handler(context, job.payload)
            if inspect.isawaitable(value):
                value = asyncio.run(_await_handler_result(value))
            self._validate_output(job.task, cast("JSONValue", value))
            if context.cancellation_requested():
                self.engine.confirm_cancel(attempt.id, worker_id=self.worker_id)
            else:
                self.engine.succeed(
                    attempt.id,
                    worker_id=self.worker_id,
                    result=cast("JSONValue", value),
                    duration_ms=int((monotonic() - start) * 1000),
                )
        except StaleAttemptError:
            # A newer attempt or a recovery operation has fenced this worker.
            _LOG.warning("Worker result fenced for attempt %s", attempt.id)
        except Exception as error:  # noqa: BLE001 - tasks may raise any user-defined exception
            # Never persist the raw exception message: it may contain secrets.
            code = (
                ErrorCode.VALIDATION_ERROR
                if isinstance(error, _SchemaRejected)
                else ErrorCode.EXECUTION_ERROR
            )
            underlying_error = error.__cause__ if isinstance(error, _SchemaRejected) else error
            try:
                self.engine.fail(
                    attempt.id,
                    worker_id=self.worker_id,
                    retryable=code is ErrorCode.EXECUTION_ERROR,
                    code=code,
                    message="Task execution failed",
                    exception_type=type(underlying_error).__name__,
                    duration_ms=int((monotonic() - start) * 1000),
                )
            except StaleAttemptError:
                _LOG.warning("Failed result fenced for attempt %s", attempt.id)
        finally:
            stop.set()
            thread.join(timeout=1)
        return True

    def run_forever(self, *, stop: Event, recovery_limit: int = 100) -> None:
        """Poll until a caller-provided stop event is set."""
        while not stop.is_set():
            self.engine.reap_expired(limit=recovery_limit)
            if not self.run_once():
                stop.wait(self.poll_interval.total_seconds())
