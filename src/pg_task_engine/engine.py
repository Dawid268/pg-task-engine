"""PostgreSQL-backed, fenced and transactional durable task queue.

All SQL is parameterized, state changes use short transactions, and execution
is deliberately performed outside transactions by :mod:`pg_task_engine.worker`.
"""

import hashlib
import json
import re
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from importlib.resources import files
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from pg_task_engine._postgresql import INT64_MAX, require_utf8
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
from pg_task_engine.job_progress import JobProgress
from pg_task_engine.job_request import (
    ExecutionPolicy,
    JobRequest,
    JSONPayload,
    JSONValue,
    _validate_json_value,
)
from pg_task_engine.job_status import JobStatus
from pg_task_engine.task_ref import TaskRef

type Handler = Callable[..., object]
type Row = dict[str, Any]
_MAX_JSON_BYTES = 65_536


class TaskEngineError(Exception):
    """Base class for expected domain and storage-level operation errors."""


class JobNotFoundError(TaskEngineError):
    """No persisted Job or attempt exists for the requested identifier."""


class UnknownTaskError(TaskEngineError):
    """Task name/version was not registered in this engine instance."""


class IdempotencyConflictError(TaskEngineError):
    """The same idempotency key was used for a different normalized request."""


class InvalidTransitionError(TaskEngineError):
    """A domain state transition or monotonic update is not allowed."""


class StaleAttemptError(TaskEngineError):
    """The worker's attempt/lease no longer authorizes writes."""


class MigrationError(TaskEngineError):
    """Applied migrations are missing, modified, or newer than this installation."""


def _bundled_migrations() -> list[tuple[int, str, str]]:
    """Read strictly numbered SQL assets in upgrade order.

    The hash is computed from the original bytes and records the exact
    migration published with this library version.
    """
    assets: list[tuple[int, str, str]] = []
    directory = files("pg_task_engine").joinpath("migrations")
    for asset in directory.iterdir():
        if not asset.is_file() or not asset.name.endswith(".sql"):
            continue
        match = re.fullmatch(r"(\d{3,})_[a-z][a-z0-9_]*\.sql", asset.name)
        if match is None:
            raise MigrationError(f"Invalid numbered migration filename: {asset.name}")
        version = int(match.group(1))
        content = asset.read_bytes()
        assets.append((version, hashlib.sha256(content).hexdigest(), content.decode("utf-8")))
    assets.sort(key=lambda item: item[0])
    if not assets or [version for version, _, _ in assets] != list(range(1, len(assets) + 1)):
        raise MigrationError("Bundled SQL migrations must have consecutive versions from 001")
    return assets


def _row_required(row: Row | None, identifier: UUID) -> Row:
    if row is None:
        raise JobNotFoundError(f"Job or attempt does not exist: {identifier}")
    return row


def _json_bytes(value: object) -> bytes:
    """Validate an arbitrary JSON value, including a successful JSON null."""
    try:
        _validate_json_value(value, set())
        result = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError("result must be valid JSON") from error
    if len(result) > _MAX_JSON_BYTES:
        raise ValueError("result cannot exceed 65536 serialized UTF-8 bytes")
    return result


class TaskEngine[QueueT: StrEnum]:
    """Installable PostgreSQL task engine with explicit migration and task registry."""

    def __init__(
        self,
        dsn: str,
        *,
        queue_enum: type[QueueT],
        default_queue: QueueT,
        defaults: EngineDefaults | None = None,
        pool_size: int = 10,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("dsn must be a nonempty PostgreSQL connection string")
        if not isinstance(queue_enum, type) or not issubclass(queue_enum, StrEnum):
            raise TypeError("queue_enum must be an application-defined StrEnum subclass")
        if queue_enum is JobStatus:
            raise TypeError("JobStatus cannot be a queue enum")
        if type(default_queue) is not queue_enum:
            raise TypeError("default_queue must belong to queue_enum")
        if defaults is not None and not isinstance(defaults, EngineDefaults):
            raise TypeError("defaults must be EngineDefaults or None")
        if type(pool_size) is not int or pool_size < 1:
            raise ValueError("pool_size must be a positive integer")

        self.dsn = dsn
        self.queue_enum = queue_enum
        self.default_queue = default_queue
        self.defaults = defaults if defaults is not None else EngineDefaults()
        self._registered: set[TaskRef] = set()
        self._handlers: dict[TaskRef, Handler] = {}
        self._input_validators: dict[TaskRef, Callable[[JSONPayload], None]] = {}
        self._output_validators: dict[TaskRef, Callable[[JSONValue], None]] = {}
        self._pool: ConnectionPool[Connection[DictRow]] = ConnectionPool(
            conninfo=dsn,
            connection_class=Connection[DictRow],
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=pool_size,
            open=True,
        )

    def __enter__(self) -> "TaskEngine[QueueT]":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Release all pooled connections and worker threads owned by the pool."""
        self._pool.close()

    def migrate(self) -> None:
        """Apply every pending numbered SQL migration in a locked transaction.

        Verify SHA-256 of previously applied assets and reject databases with
        missing or unknown revisions. Upgrades from the legacy 001-only
        metadata table populate its missing checksum once.
        """
        migrations = _bundled_migrations()
        known = {version: checksum for version, checksum, _ in migrations}
        with self._pool.connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (6_010_013_001,))
            conn.execute("CREATE SCHEMA IF NOT EXISTS task_engine")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS task_engine.schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL "
                "DEFAULT clock_timestamp(), checksum CHAR(64))"
            )
            # Compatibility with installations using the original 001-only runner.
            conn.execute(
                "ALTER TABLE task_engine.schema_migrations "
                "ADD COLUMN IF NOT EXISTS checksum CHAR(64)"
            )
            rows = conn.execute(
                "SELECT version, checksum FROM task_engine.schema_migrations ORDER BY version"
            ).fetchall()
            installed = {int(row["version"]): row["checksum"] for row in rows}
            if any(version not in known for version in installed):
                raise MigrationError("Database has a newer or unknown migration version")
            if sorted(installed) != list(range(1, len(installed) + 1)):
                raise MigrationError("Database migration versions contain a gap")

            for version, recorded in installed.items():
                expected = known[version]
                if recorded is None:
                    # Version 001 predates checksummed metadata. Backfill only
                    # during an upgrade from the original one-version layout.
                    if version != 1 or len(installed) != 1:
                        raise MigrationError(f"Missing checksum for migration {version:03d}")
                    conn.execute(
                        "UPDATE task_engine.schema_migrations SET checksum = %s WHERE version = %s",
                        (expected, version),
                    )
                elif recorded != expected:
                    raise MigrationError(f"SQL migration checksum mismatch for {version:03d}")

            for version, checksum, sql in migrations:
                if version in installed:
                    continue
                conn.execute(sql, prepare=False)
                conn.execute(
                    "INSERT INTO task_engine.schema_migrations(version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
            conn.execute(
                "ALTER TABLE task_engine.schema_migrations ALTER COLUMN checksum SET NOT NULL"
            )

    def register(
        self,
        task: TaskRef,
        handler: Handler | None = None,
        *,
        input_validator: Callable[[JSONPayload], None] | None = None,
        output_validator: Callable[[JSONValue], None] | None = None,
    ) -> None:
        """Register a stable task version, its handler and optional schema hooks.

        Schema hooks should raise ValueError on invalid data. The engine runs
        the input hook at enqueue AND immediately before worker execution.
        """
        if not isinstance(task, TaskRef):
            raise TypeError("task must be a TaskRef")
        if handler is not None and not callable(handler):
            raise TypeError("handler must be callable")
        if input_validator is not None and not callable(input_validator):
            raise TypeError("input_validator must be callable")
        if output_validator is not None and not callable(output_validator):
            raise TypeError("output_validator must be callable")
        self._registered.add(task)
        if handler is not None:
            self._handlers[task] = handler
        if input_validator is not None:
            self._input_validators[task] = input_validator
        if output_validator is not None:
            self._output_validators[task] = output_validator

    def handler_for(self, task: TaskRef) -> Handler:
        try:
            return self._handlers[task]
        except KeyError as error:
            raise UnknownTaskError(f"No worker handler for {task.name}:{task.version}") from error

    @property
    def runnable_tasks(self) -> frozenset[TaskRef]:
        """Task versions this engine instance can actually execute."""
        return frozenset(self._handlers)

    def validate_input(self, task: TaskRef, payload: JSONPayload) -> None:
        """Apply a version-specific input schema to an isolated JSON copy."""
        validator = self._input_validators.get(task)
        if validator is not None:
            validator(cast("JSONPayload", json.loads(_json_bytes(payload))))

    def validate_output(self, task: TaskRef, value: JSONValue) -> None:
        """Validate JSON even without an optional task-specific result schema."""
        isolated = cast("JSONValue", json.loads(_json_bytes(value)))
        validator = self._output_validators.get(task)
        if validator is not None:
            validator(isolated)

    def enqueue_task(
        self,
        task: TaskRef,
        *,
        payload: JSONPayload | None = None,
        queue: QueueT | None = None,
        not_before: datetime | None = None,
        execution_policy: ExecutionPolicy | None = None,
        idempotency_key: str | None = None,
    ) -> JobSnapshot[QueueT]:
        """Convenience SDK entry point resolving the engine's default queue."""
        request: JobRequest[QueueT] = JobRequest(
            task=task,
            queue=queue if queue is not None else self.default_queue,
            payload=payload if payload is not None else {},
            not_before=not_before,
            execution_policy=execution_policy,
            idempotency_key=idempotency_key,
        )
        return self.enqueue(request)

    def _resolved_policy(self, requested: ExecutionPolicy | None) -> ResolvedPolicy:
        chosen = requested if requested is not None else ExecutionPolicy()
        return ResolvedPolicy(
            max_attempts=(
                chosen.max_attempts
                if chosen.max_attempts is not None
                else self.defaults.max_attempts
            ),
            timeout=chosen.timeout if chosen.timeout is not None else self.defaults.timeout,
            retry_delay=(
                chosen.retry_delay if chosen.retry_delay is not None else self.defaults.retry_delay
            ),
        )

    def _fingerprint(self, request: JobRequest[QueueT]) -> str:
        """Hash normalized caller intent, not the generated job creation time."""
        # Explicit ExecutionPolicy() is equivalent to no overrides at all.
        policy = request.execution_policy or ExecutionPolicy()
        document = {
            "task": [request.task.name, request.task.version],
            "queue": request.queue.value,
            "payload": request.payload,
            "not_before": request.not_before.isoformat() if request.not_before else None,
            "policy": {
                "max_attempts": policy.max_attempts,
                "timeout_microseconds": (
                    policy.timeout // timedelta(microseconds=1) if policy.timeout else None
                ),
                "retry_delay_microseconds": (
                    policy.retry_delay // timedelta(microseconds=1) if policy.retry_delay else None
                ),
            },
        }
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def enqueue(self, request: JobRequest[QueueT]) -> JobSnapshot[QueueT]:
        """Atomically persist one validated request or return its idempotent match."""
        if not isinstance(request, JobRequest):
            raise TypeError("request must be a JobRequest")
        if type(request.queue) is not self.queue_enum:
            raise TypeError("queue must be a member of the registered queue enum")
        if request.task not in self._registered:
            raise UnknownTaskError(
                f"Task not registered: {request.task.name}:{request.task.version}"
            )

        # Recheck and copy the caller's mutable input immediately before persistence.
        clean: JobRequest[QueueT] = JobRequest(
            task=request.task,
            queue=request.queue,
            payload=request.payload,
            not_before=request.not_before,
            execution_policy=request.execution_policy,
            idempotency_key=request.idempotency_key,
        )
        self.validate_input(clean.task, clean.payload)
        resolved = self._resolved_policy(clean.execution_policy)
        intent = self._fingerprint(clean)
        job_id = uuid4()
        with self._pool.connection() as conn:
            now_row = conn.execute("SELECT clock_timestamp() AS at").fetchone()
            if now_row is None:
                raise TaskEngineError("Database clock was unavailable")
            scheduled = clean.not_before if clean.not_before is not None else now_row["at"]
            inserted = conn.execute(
                """
                INSERT INTO task_engine.jobs (
                    id, task_name, task_version, queue, payload, status,
                    scheduled_at, available_at, max_attempts, timeout_interval,
                    retry_delay_interval, idempotency_key, intent_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, 'queued',
                    %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (idempotency_key)
                   WHERE idempotency_key IS NOT NULL
                   DO NOTHING RETURNING id
                """,
                (
                    job_id,
                    clean.task.name,
                    clean.task.version,
                    clean.queue.value,
                    Jsonb(clean.payload),
                    scheduled,
                    scheduled,
                    resolved.max_attempts,
                    resolved.timeout,
                    resolved.retry_delay,
                    clean.idempotency_key,
                    intent,
                ),
            ).fetchone()
            if inserted is None:
                conflict = conn.execute(
                    "SELECT id, intent_sha256 FROM task_engine.jobs WHERE idempotency_key = %s",
                    (clean.idempotency_key,),
                ).fetchone()
                if conflict is None or conflict["intent_sha256"] != intent:
                    raise IdempotencyConflictError(
                        "Idempotency key conflicts with a different request"
                    )
                job_id = cast("UUID", conflict["id"])
            else:
                self._event(conn, job_id, "enqueued", None, None, JobStatus.QUEUED)
            return self._snapshot(conn, job_id)

    @staticmethod
    def _event(
        conn: Connection[DictRow],
        job_id: UUID,
        type_name: str,
        attempt_id: UUID | None,
        old: JobStatus | None,
        new: JobStatus | None,
    ) -> None:
        conn.execute(
            "INSERT INTO task_engine.events"
            "(job_id, attempt_id, type, from_status, to_status)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                job_id,
                attempt_id,
                type_name,
                old.value if old is not None else None,
                new.value if new is not None else None,
            ),
        )

    def _snapshot(self, conn: Connection[DictRow], job_id: UUID) -> JobSnapshot[QueueT]:
        row = _row_required(
            conn.execute(
                """
                SELECT j.*,
                       p.completed AS progress_completed,
                       p.total AS progress_total,
                       p.unit AS progress_unit,
                       p.revision AS progress_revision,
                       p.updated_at AS progress_updated_at
                FROM task_engine.jobs j
                LEFT JOIN task_engine.progress p ON p.job_id = j.id
                WHERE j.id = %s
                """,
                (job_id,),
            ).fetchone(),
            job_id,
        )
        queue = self.queue_enum(row["queue"])
        progress = (
            JobProgress(
                completed=row["progress_completed"],
                total=row["progress_total"],
                unit=row["progress_unit"],
                revision=row["progress_revision"],
                updated_at=row["progress_updated_at"].astimezone(UTC),
            )
            if row["progress_revision"] is not None
            else None
        )
        return JobSnapshot(
            id=row["id"],
            task=TaskRef(row["task_name"], row["task_version"]),
            queue=queue,
            payload=cast("JSONPayload", row["payload"]),
            status=JobStatus(row["status"]),
            policy=ResolvedPolicy(
                max_attempts=row["max_attempts"],
                timeout=row["timeout_interval"],
                retry_delay=row["retry_delay_interval"],
            ),
            idempotency_key=row["idempotency_key"],
            created_at=row["created_at"].astimezone(UTC),
            scheduled_at=row["scheduled_at"].astimezone(UTC),
            available_at=row["available_at"].astimezone(UTC) if row["available_at"] else None,
            first_started_at=(
                row["first_started_at"].astimezone(UTC) if row["first_started_at"] else None
            ),
            finished_at=row["finished_at"].astimezone(UTC) if row["finished_at"] else None,
            attempts_count=row["attempts_count"],
            current_attempt_id=row["current_attempt_id"],
            result=JobResult(cast("JSONValue", row["result"])) if row["result_present"] else None,
            progress=progress,
            cancel_requested=row["cancel_requested"],
            revision=row["revision"],
        )

    def get(self, job_id: UUID) -> JobSnapshot[QueueT]:
        with self._pool.connection() as conn:
            return self._snapshot(conn, job_id)

    @staticmethod
    def _attempt_row(row: Row) -> JobAttempt:
        error = (
            ErrorInfo(
                code=ErrorCode(row["error_code"]),
                message=row["error_message"],
                exception_type=row["exception_type"],
            )
            if row["error_code"] is not None
            else None
        )
        return JobAttempt(
            id=row["id"],
            job_id=row["job_id"],
            number=row["number"],
            worker_id=row["worker_id"],
            status=AttemptStatus(row["status"]),
            claimed_at=row["claimed_at"].astimezone(UTC),
            started_at=row["started_at"].astimezone(UTC) if row["started_at"] else None,
            heartbeat_at=row["heartbeat_at"].astimezone(UTC),
            lease_expires_at=row["lease_expires_at"].astimezone(UTC),
            deadline_at=row["deadline_at"].astimezone(UTC) if row["deadline_at"] else None,
            finished_at=row["finished_at"].astimezone(UTC) if row["finished_at"] else None,
            execution_duration_ms=row["execution_duration_ms"],
            error=error,
        )

    def attempts(self, job_id: UUID) -> list[JobAttempt]:
        with self._pool.connection() as conn:
            records = conn.execute(
                "SELECT * FROM task_engine.attempts WHERE job_id = %s ORDER BY number",
                (job_id,),
            ).fetchall()
            return [self._attempt_row(row) for row in records]

    def events(self, job_id: UUID) -> list[JobEvent]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_engine.events WHERE job_id = %s ORDER BY id",
                (job_id,),
            ).fetchall()
            return [
                JobEvent(
                    id=row["id"],
                    job_id=row["job_id"],
                    attempt_id=row["attempt_id"],
                    type=row["type"],
                    from_status=JobStatus(row["from_status"]) if row["from_status"] else None,
                    to_status=JobStatus(row["to_status"]) if row["to_status"] else None,
                    created_at=row["created_at"].astimezone(UTC),
                )
                for row in rows
            ]

    def claim(
        self,
        queue: QueueT,
        *,
        worker_id: UUID,
        supported_tasks: Collection[TaskRef] | None = None,
    ) -> JobAttempt | None:
        """Atomically lease the earliest ready Job using SKIP LOCKED.

        Only one transaction can claim a particular job. Attempts are counted
        *at claim*, even if the worker never starts executing its handler.
        Workers can restrict claims to locally supported name/version pairs.
        Manual or remote executors may omit the optional filter.
        """
        if type(queue) is not self.queue_enum:
            raise TypeError("queue must belong to the registered queue enum")
        if not isinstance(worker_id, UUID):
            raise TypeError("worker_id must be a UUID")
        task_filter: tuple[TaskRef, ...] = ()
        if supported_tasks is not None:
            task_filter = tuple(supported_tasks)
            if not all(isinstance(task, TaskRef) for task in task_filter):
                raise TypeError("supported_tasks must contain only TaskRef instances")
            if not task_filter:
                return None
        with self._pool.connection() as conn:
            candidate = conn.execute(
                """
                SELECT id, status, attempts_count
                FROM task_engine.jobs
                WHERE queue = %s
                  AND status IN ('queued', 'retry_scheduled')
                  AND available_at <= clock_timestamp()
                  AND attempts_count < max_attempts
                  AND (
                      %s::boolean
                      OR (task_name, task_version) IN (
                          SELECT accepted.name, accepted.version
                          FROM unnest(%s::text[], %s::integer[]) AS accepted(name, version)
                      )
                  )
                ORDER BY available_at, created_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (
                    queue.value,
                    supported_tasks is None,
                    [task.name for task in task_filter],
                    [task.version for task in task_filter],
                ),
            ).fetchone()
            if candidate is None:
                return None
            job_id = cast("UUID", candidate["id"])
            attempt_id = uuid4()
            now_row = conn.execute("SELECT clock_timestamp() AS now").fetchone()
            if now_row is None:
                raise TaskEngineError("Database clock was unavailable")
            now = cast("datetime", now_row["now"])
            conn.execute(
                """
                UPDATE task_engine.jobs
                SET status = 'running', attempts_count = attempts_count + 1,
                    available_at = NULL, current_attempt_id = %s,
                    revision = revision + 1
                WHERE id = %s
                """,
                (attempt_id, job_id),
            )
            created = conn.execute(
                """
                INSERT INTO task_engine.attempts
                    (id, job_id, number, worker_id, status,
                     claimed_at, heartbeat_at, lease_expires_at)
                VALUES (%s, %s, %s, %s, 'claimed', %s, %s, %s)
                RETURNING *
                """,
                (
                    attempt_id,
                    job_id,
                    candidate["attempts_count"] + 1,
                    worker_id,
                    now,
                    now,
                    now + self.defaults.lease_duration,
                ),
            ).fetchone()
            self._event(
                conn,
                job_id,
                "claimed",
                attempt_id,
                JobStatus(candidate["status"]),
                JobStatus.RUNNING,
            )
            if created is None:
                raise TaskEngineError("Claimed attempt row was not returned")
            return self._attempt_row(created)

    @staticmethod
    def _active_attempt(
        conn: Connection[DictRow], attempt_id: UUID, worker_id: UUID
    ) -> tuple[Row, datetime]:
        """Lock a Job and Attempt, then verify fencing and DB clock deadlines."""
        row = conn.execute(
            """
            SELECT a.*, j.status AS job_status,
                   j.current_attempt_id, j.timeout_interval,
                   j.retry_delay_interval, j.max_attempts, j.attempts_count,
                   j.cancel_requested
            FROM task_engine.attempts a
            JOIN task_engine.jobs j ON j.id = a.job_id
            WHERE a.id = %s
            FOR UPDATE OF a, j
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise StaleAttemptError("Attempt does not exist or is not active")
        now_row = conn.execute("SELECT clock_timestamp() AS now").fetchone()
        if now_row is None:
            raise TaskEngineError("Database clock was unavailable")
        now = cast("datetime", now_row["now"])
        if (
            row["current_attempt_id"] != attempt_id
            or row["worker_id"] != worker_id
            or row["job_status"] != JobStatus.RUNNING
            or row["status"] not in (AttemptStatus.CLAIMED, AttemptStatus.RUNNING)
            or row["lease_expires_at"] <= now
            or (row["deadline_at"] is not None and row["deadline_at"] <= now)
        ):
            raise StaleAttemptError("Expired lease, deadline or superseded attempt")
        return row, now

    def start(self, attempt_id: UUID, *, worker_id: UUID) -> JobAttempt:
        """Confirm real execution start; deadline begins *now*, not at claim."""
        with self._pool.connection() as conn:
            row, now = self._active_attempt(conn, attempt_id, worker_id)
            if row["status"] != AttemptStatus.CLAIMED:
                raise InvalidTransitionError("Attempt already started")
            conn.execute(
                """
                UPDATE task_engine.attempts
                SET status = 'running', started_at = %s, deadline_at = %s
                WHERE id = %s
                """,
                (now, now + row["timeout_interval"], attempt_id),
            )
            conn.execute(
                """
                UPDATE task_engine.jobs
                SET first_started_at = COALESCE(first_started_at, %s),
                    revision = revision + 1
                WHERE id = %s
                """,
                (now, row["job_id"]),
            )
            self._event(conn, row["job_id"], "started", attempt_id, None, None)
            updated = conn.execute(
                "SELECT * FROM task_engine.attempts WHERE id = %s",
                (attempt_id,),
            ).fetchone()
            if updated is None:
                raise TaskEngineError("Started attempt was not returned")
            return self._attempt_row(updated)

    def heartbeat(self, attempt_id: UUID, *, worker_id: UUID) -> JobAttempt:
        """Extend the lease without ever modifying the execution deadline."""
        with self._pool.connection() as conn:
            row, now = self._active_attempt(conn, attempt_id, worker_id)
            updated = conn.execute(
                """
                UPDATE task_engine.attempts
                SET heartbeat_at = %s, lease_expires_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, now + self.defaults.lease_duration, row["id"]),
            ).fetchone()
            if updated is None:
                raise TaskEngineError("Heartbeated attempt was not returned")
            return self._attempt_row(updated)

    def succeed(
        self,
        attempt_id: UUID,
        *,
        worker_id: UUID,
        result: JSONValue,
        duration_ms: int | None = None,
    ) -> JobSnapshot[QueueT]:
        """Accept the result only from the current, valid attempt token."""
        serialized = _json_bytes(result)
        if duration_ms is not None and (
            type(duration_ms) is not int or not 0 <= duration_ms <= INT64_MAX
        ):
            raise ValueError("duration_ms must fit non-negative PostgreSQL BIGINT or be None")
        safe_result = cast("JSONValue", json.loads(serialized))
        with self._pool.connection() as conn:
            row, now = self._active_attempt(conn, attempt_id, worker_id)
            if row["status"] != AttemptStatus.RUNNING:
                raise InvalidTransitionError("Attempt must be RUNNING to succeed")
            conn.execute(
                """
                UPDATE task_engine.attempts
                SET status = 'succeeded', finished_at = %s,
                    execution_duration_ms = %s
                WHERE id = %s
                """,
                (now, duration_ms, attempt_id),
            )
            conn.execute(
                """
                UPDATE task_engine.jobs
                SET status = 'succeeded', finished_at = %s,
                    current_attempt_id = NULL, result_present = TRUE,
                    result = %s, revision = revision + 1
                WHERE id = %s
                """,
                (now, Jsonb(safe_result), row["job_id"]),
            )
            self._event(
                conn,
                row["job_id"],
                "succeeded",
                attempt_id,
                JobStatus.RUNNING,
                JobStatus.SUCCEEDED,
            )
            return self._snapshot(conn, row["job_id"])

    @staticmethod
    def _finish_error(
        conn: Connection[DictRow],
        row: Row,
        now: datetime,
        *,
        final_attempt_status: AttemptStatus,
        retryable: bool,
        code: ErrorCode,
        message: str,
        exception_type: str | None,
        duration_ms: int | None = None,
    ) -> JobStatus:
        """Close both Attempt and Job in one transaction with explicit retry."""
        allowed_retry = retryable and row["attempts_count"] < row["max_attempts"]
        next_status = JobStatus.RETRY_SCHEDULED if allowed_retry else JobStatus.FAILED
        conn.execute(
            """
            UPDATE task_engine.attempts
            SET status = %s, finished_at = %s, execution_duration_ms = %s,
                error_code = %s, error_message = %s, exception_type = %s
            WHERE id = %s
            """,
            (
                final_attempt_status.value,
                now,
                duration_ms,
                code.value,
                message[:512],
                exception_type,
                row["id"],
            ),
        )
        conn.execute(
            """
            UPDATE task_engine.jobs
            SET status = %s, available_at = %s, finished_at = %s,
                current_attempt_id = NULL, revision = revision + 1
            WHERE id = %s
            """,
            (
                next_status.value,
                now + row["retry_delay_interval"] if allowed_retry else None,
                None if allowed_retry else now,
                row["job_id"],
            ),
        )
        TaskEngine._event(
            conn,
            row["job_id"],
            "retry_scheduled" if allowed_retry else "failed",
            row["id"],
            JobStatus.RUNNING,
            next_status,
        )
        return next_status

    def fail(
        self,
        attempt_id: UUID,
        *,
        worker_id: UUID,
        retryable: bool = True,
        code: ErrorCode | str = ErrorCode.EXECUTION_ERROR,
        message: str = "Task execution failed",
        exception_type: str | None = None,
        duration_ms: int | None = None,
    ) -> JobSnapshot[QueueT]:
        """Record a failed attempt without recording raw exception messages."""
        if type(retryable) is not bool:
            raise TypeError("retryable must be a bool")
        safe_code = ErrorCode(code)
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        if "\x00" in message:
            raise ValueError("message must not contain PostgreSQL-incompatible NUL characters")
        require_utf8(message, field="message")
        if exception_type is not None and not isinstance(exception_type, str):
            raise TypeError("exception_type must be a string or None")
        if exception_type is not None and "\x00" in exception_type:
            raise ValueError("exception_type must not contain NUL characters")
        if exception_type is not None:
            require_utf8(exception_type, field="exception_type")
        if duration_ms is not None and (
            type(duration_ms) is not int or not 0 <= duration_ms <= INT64_MAX
        ):
            raise ValueError("duration_ms must fit non-negative PostgreSQL BIGINT or be None")
        with self._pool.connection() as conn:
            row, now = self._active_attempt(conn, attempt_id, worker_id)
            if row["status"] != AttemptStatus.RUNNING:
                raise InvalidTransitionError("Attempt must be RUNNING to fail")
            self._finish_error(
                conn,
                row,
                now,
                final_attempt_status=AttemptStatus.FAILED,
                retryable=retryable,
                code=safe_code,
                message=message,
                exception_type=exception_type,
                duration_ms=duration_ms,
            )
            return self._snapshot(conn, row["job_id"])

    def save_progress(
        self,
        attempt_id: UUID,
        *,
        worker_id: UUID,
        completed: int,
        total: int | None,
        unit: str,
        revision: int,
    ) -> JobProgress:
        """Monotonic, token-fenced progress update from the active attempt."""
        with self._pool.connection() as conn:
            row, now = self._active_attempt(conn, attempt_id, worker_id)
            if row["status"] != AttemptStatus.RUNNING:
                raise InvalidTransitionError("Attempt must be running to save progress")
            progress = JobProgress(
                completed=completed,
                total=total,
                unit=unit,
                revision=revision,
                updated_at=now.astimezone(UTC),
            )
            stored = conn.execute(
                """
                INSERT INTO task_engine.progress
                    (job_id, completed, total, unit, revision, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    completed = EXCLUDED.completed,
                    total = EXCLUDED.total,
                    unit = EXCLUDED.unit,
                    revision = EXCLUDED.revision,
                    updated_at = EXCLUDED.updated_at
                WHERE task_engine.progress.revision < EXCLUDED.revision
                RETURNING revision
                """,
                (row["job_id"], completed, total, unit, revision, now),
            ).fetchone()
            if stored is None:
                raise InvalidTransitionError("Progress revision must increase")
            self._event(conn, row["job_id"], "progress_updated", attempt_id, None, None)
            return progress

    def request_cancel(self, job_id: UUID) -> JobSnapshot[QueueT]:
        """Cancel waiting work, or mark active work for cooperative cancellation."""
        with self._pool.connection() as conn:
            row = _row_required(
                conn.execute(
                    "SELECT id, status, cancel_requested FROM task_engine.jobs "
                    "WHERE id = %s FOR UPDATE",
                    (job_id,),
                ).fetchone(),
                job_id,
            )
            current = JobStatus(row["status"])
            if current in (JobStatus.QUEUED, JobStatus.RETRY_SCHEDULED):
                conn.execute(
                    """
                    UPDATE task_engine.jobs
                    SET status = 'cancelled', available_at = NULL,
                        finished_at = clock_timestamp(), revision = revision + 1
                    WHERE id = %s
                    """,
                    (job_id,),
                )
                self._event(conn, job_id, "cancelled", None, current, JobStatus.CANCELLED)
            elif current is JobStatus.RUNNING and not row["cancel_requested"]:
                conn.execute(
                    """
                    UPDATE task_engine.jobs
                    SET cancel_requested = TRUE, revision = revision + 1
                    WHERE id = %s
                    """,
                    (job_id,),
                )
                self._event(conn, job_id, "cancel_requested", None, None, None)
            return self._snapshot(conn, job_id)

    def confirm_cancel(self, attempt_id: UUID, *, worker_id: UUID) -> JobSnapshot[QueueT]:
        """Only a valid active worker may confirm that it stopped safely."""
        with self._pool.connection() as conn:
            row, now = self._active_attempt(conn, attempt_id, worker_id)
            if not row["cancel_requested"]:
                raise InvalidTransitionError("No cancellation request exists")
            conn.execute(
                """
                UPDATE task_engine.attempts
                SET status = 'failed', finished_at = %s,
                    error_code = %s, error_message = 'Task cancelled safely'
                WHERE id = %s
                """,
                (now, ErrorCode.CANCELLED.value, attempt_id),
            )
            conn.execute(
                """
                UPDATE task_engine.jobs
                SET status = 'cancelled', current_attempt_id = NULL,
                    finished_at = %s, revision = revision + 1
                WHERE id = %s
                """,
                (now, row["job_id"]),
            )
            self._event(
                conn,
                row["job_id"],
                "cancelled",
                attempt_id,
                JobStatus.RUNNING,
                JobStatus.CANCELLED,
            )
            return self._snapshot(conn, row["job_id"])

    def reap_expired(self, limit: int = 100) -> int:
        """Recover orphaned attempts without trusting a stale worker's writes."""
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.job_id, a.deadline_at, a.lease_expires_at,
                       j.current_attempt_id, j.retry_delay_interval,
                       j.max_attempts, j.attempts_count
                FROM task_engine.attempts a
                JOIN task_engine.jobs j ON j.current_attempt_id = a.id
                WHERE j.status = 'running'
                  AND a.status IN ('claimed', 'running')
                  AND (
                       a.lease_expires_at <= clock_timestamp()
                       OR (a.deadline_at IS NOT NULL AND a.deadline_at <= clock_timestamp())
                  )
                ORDER BY a.lease_expires_at, a.id
                FOR UPDATE OF a, j SKIP LOCKED LIMIT %s
                """,
                (limit,),
            ).fetchall()
            for row in rows:
                now_row = conn.execute("SELECT clock_timestamp() AS now").fetchone()
                if now_row is None:
                    raise TaskEngineError("Database clock was unavailable")
                now = cast("datetime", now_row["now"])
                timed_out = row["deadline_at"] is not None and row["deadline_at"] <= now
                self._finish_error(
                    conn,
                    row,
                    now,
                    final_attempt_status=(
                        AttemptStatus.TIMED_OUT if timed_out else AttemptStatus.LOST
                    ),
                    retryable=True,
                    code=ErrorCode.TIMEOUT if timed_out else ErrorCode.LEASE_LOST,
                    message="Task deadline reached" if timed_out else "Worker lease expired",
                    exception_type=None,
                )
            return len(rows)
