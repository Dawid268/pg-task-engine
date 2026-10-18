from dataclasses import dataclass
from datetime import datetime, timedelta

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
        self._validate_counts()
        self._validate_revision()
        self._validate_unit()
        self._validate_updated_at()

    def _validate_counts(self) -> None:
        if type(self.completed) is not int:
            raise JobProgressTypeError(JobProgressErrorCode.COMPLETED_NOT_INTEGER)
        if self.completed < 0:
            raise JobProgressValueError(JobProgressErrorCode.COMPLETED_NEGATIVE)
        if type(self.total) is not int and self.total is not None:
            raise JobProgressTypeError(JobProgressErrorCode.TOTAL_NOT_INTEGER)
        if self.total is not None and self.total < 0:
            raise JobProgressValueError(JobProgressErrorCode.TOTAL_NEGATIVE)
        if self.total is not None and self.completed > self.total:
            raise JobProgressValueError(JobProgressErrorCode.COMPLETED_EXCEEDS_TOTAL)

    def _validate_revision(self) -> None:
        if type(self.revision) is not int:
            raise JobProgressTypeError(JobProgressErrorCode.REVISION_NOT_INTEGER)
        if self.revision < 0:
            raise JobProgressValueError(JobProgressErrorCode.REVISION_NEGATIVE)

    def _validate_unit(self) -> None:
        if type(self.unit) is not str:
            raise JobProgressTypeError(JobProgressErrorCode.UNIT_TYPE_ERROR)
        if self.unit.strip() == "":
            raise JobProgressValueError(JobProgressErrorCode.UNIT_EMPTY)
        if "\x00" in self.unit:
            raise JobProgressValueError(JobProgressErrorCode.UNIT_CONTAINS_NUL)

    def _validate_updated_at(self) -> None:
        if not isinstance(self.updated_at, datetime):
            raise JobProgressTypeError(JobProgressErrorCode.UPDATED_AT_TYPE_ERROR)
        utc_offset = self.updated_at.utcoffset()
        if utc_offset is None:
            raise JobProgressValueError(JobProgressErrorCode.UPDATED_AT_NAIVE)
        if utc_offset != timedelta(0):
            raise JobProgressValueError(JobProgressErrorCode.UPDATED_AT_NOT_UTC)
