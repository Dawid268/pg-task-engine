from pg_task_engine.job_status import JobStatus, can_transition


def test_queued_job_can_start() -> None:
    current_status = JobStatus.QUEUED
    target_status = JobStatus.RUNNING

    result = can_transition(current_status, target_status)

    assert result is True


def test_failed_job_cannot_restart() -> None:
    current_status = JobStatus.FAILED
    target_status = JobStatus.RUNNING

    result = can_transition(current_status, target_status)

    assert result is False
