"""Administrative and worker commands for a trusted local application factory.

The `module:factory` value is chosen by the operator, never by a job payload.
"""

import argparse
import importlib
import json
import os
import signal
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Event
from typing import cast
from uuid import UUID

from pg_task_engine.engine import TaskEngine
from pg_task_engine.job_request import JSONPayload
from pg_task_engine.task_ref import TaskRef
from pg_task_engine.worker import Worker


class _MigrationQueue(StrEnum):
    ADMIN = "admin"


def _load_engine(locator: str, *, app_path: str | None = None) -> TaskEngine[StrEnum]:
    if ":" not in locator:
        raise ValueError("App factory must use 'module:function' syntax")
    if app_path is not None:
        directory = Path(app_path).resolve()
        if not directory.is_dir():
            raise ValueError("Operator-supplied --app-path must be an existing directory")
        # Explicit operator trust decision: never derive an import path from
        # a task payload or from persisted untrusted JSON.
        sys.path.insert(0, str(directory))
    module_name, factory_name = locator.split(":", maxsplit=1)
    if not module_name or not factory_name:
        raise ValueError("App factory must use 'module:function' syntax")
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise ValueError("App factory does not exist or is not callable")
    engine = factory()
    if not isinstance(engine, TaskEngine):
        raise TypeError("App factory must return a TaskEngine")
    return cast("TaskEngine[StrEnum]", engine)


def _encode_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    raise TypeError(f"Cannot encode object of type {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    """CLI used for migrations, enqueueing, inspecting and running workers."""
    parser = argparse.ArgumentParser(prog="pg-task-engine")
    commands = parser.add_subparsers(dest="command", required=True)

    migration = commands.add_parser("migrate", help="Apply explicit PostgreSQL migrations")
    migration.add_argument(
        "--dsn", default=os.environ.get("TASK_ENGINE_DSN"), help="PostgreSQL DSN"
    )

    work = commands.add_parser("worker", help="Run a worker for a registered queue")
    work.add_argument("--app", required=True, help="Trusted module:engine_factory")
    work.add_argument("--app-path", help="Operator-trusted Python module root")
    work.add_argument("--queue", required=True, help="Value from application's queue enum")
    work.add_argument("--poll-seconds", type=float, default=1.0)

    enqueue = commands.add_parser("enqueue", help="Enqueue a registered task")
    enqueue.add_argument("--app", required=True, help="Trusted module:engine_factory")
    enqueue.add_argument("--app-path", help="Operator-trusted Python module root")
    enqueue.add_argument("--task", required=True, help="Registered task name")
    enqueue.add_argument("--version", type=int, required=True)
    enqueue.add_argument("--queue", help="Queue value; omit for default")
    enqueue.add_argument("--payload", default="{}", help="JSON object (no shell secrets)")
    enqueue.add_argument("--idempotency-key")

    inspect = commands.add_parser("inspect", help="Read a persisted Job snapshot")
    inspect.add_argument("--app", required=True, help="Trusted module:engine_factory")
    inspect.add_argument("--app-path", help="Operator-trusted Python module root")
    inspect.add_argument("--job-id", required=True, help="UUID")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        if not args.dsn:
            parser.error("migrate requires --dsn or TASK_ENGINE_DSN")
        with TaskEngine(
            args.dsn,
            queue_enum=_MigrationQueue,
            default_queue=_MigrationQueue.ADMIN,
        ) as migration_engine:
            migration_engine.migrate()
        sys.stdout.write("Database migrations applied\n")
        return 0

    with _load_engine(args.app, app_path=args.app_path) as engine:
        if args.command == "worker":
            worker_queue = engine.queue_enum(args.queue)
            worker = Worker(
                engine,
                queue=worker_queue,
                poll_interval=timedelta(seconds=args.poll_seconds),
            )
            stopping = Event()

            def handle_stop(_signum: int, _frame: object) -> None:
                stopping.set()

            signal.signal(signal.SIGINT, handle_stop)
            signal.signal(signal.SIGTERM, handle_stop)
            worker.run_forever(stop=stopping)
            return 0

        if args.command == "enqueue":
            payload = json.loads(args.payload)
            if not isinstance(payload, dict):
                parser.error("payload must be a JSON object")
            requested_queue = engine.queue_enum(args.queue) if args.queue else None
            job = engine.enqueue_task(
                TaskRef(args.task, args.version),
                queue=requested_queue,
                payload=cast("JSONPayload", payload),
                idempotency_key=args.idempotency_key,
            )
            sys.stdout.write(f"{job.id}\n")
            return 0

        if args.command == "inspect":
            snapshot = engine.get(UUID(args.job_id))
            sys.stdout.write(
                json.dumps(asdict(snapshot), indent=2, ensure_ascii=False, default=_encode_value)
                + "\n"
            )
            return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
