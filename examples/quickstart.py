"""Run: TASK_ENGINE_DSN=postgresql://... uv run python -m examples.quickstart

The trusted CLI may also use --app examples.quickstart:build_engine.
No external SMTP API is called: this is a working persistence demonstration.
"""

import os
from enum import StrEnum

from pg_task_engine import (
    JSONPayload,
    JSONValue,
    TaskContext,
    TaskEngine,
    TaskRef,
    Worker,
)


class AppQueue(StrEnum):
    EMAILS = "emails"
    REPORTS = "reports"


SEND_EMAIL = TaskRef("send_email", 1)


def send_email(context: TaskContext[AppQueue], payload: JSONPayload) -> JSONValue:
    """Demonstrate a cooperative task; a real app would invoke its mail adapter."""
    context.save_progress(completed=1, total=1, unit="messages", revision=1)
    return {"acknowledged": payload["recipient"]}


def build_engine() -> TaskEngine[AppQueue]:
    """Factory explicitly selected by a trusted worker or CLI operator."""
    dsn = os.environ["TASK_ENGINE_DSN"]
    engine = TaskEngine(dsn, queue_enum=AppQueue, default_queue=AppQueue.EMAILS)
    engine.register(SEND_EMAIL, handler=send_email)
    return engine


def main() -> None:
    with build_engine() as engine:
        engine.migrate()
        job = engine.enqueue_task(
            SEND_EMAIL,
            payload={"recipient": "demo@example.test"},
            idempotency_key="quickstart-demo",
        )
        Worker(engine, queue=AppQueue.EMAILS).run_once()
        result = engine.get(job.id)
        print(f"Job {result.id}: {result.status.value}, result={result.result!r}")  # noqa: T201


if __name__ == "__main__":
    main()
