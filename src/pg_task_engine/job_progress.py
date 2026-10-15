from dataclasses import dataclass
from datetime import datetime

from pg_task_engine.job_progress_errors import (
    JobProgressErrorCode,
    JobProgressTypeError,
    JobProgressValueError,
)


@dataclass(frozen=True, slots=True)
class JobProgress:
    completed: int
    total: int | None
    unit: str
    revision: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if type(self.completed) is not int:
            raise JobProgressTypeError(JobProgressErrorCode.COMPLETED_NOT_INTEGER)
        if self.completed < 0:
            raise JobProgressValueError(JobProgressErrorCode.COMPLETED_NEGATIVE)
        if type(self.total) is not int and self.total is not None:
            raise JobProgressTypeError(JobProgressErrorCode.TOTAL_NOT_INTEGER)
        if self.total is not None and self.total < 0:
            raise JobProgressValueError(JobProgressErrorCode.TOTAL_NEGATIVE)
