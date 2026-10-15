"""Stable validation error codes for JobProgress.

Callers should branch on an error code, not on the human-readable message.
"""

from enum import StrEnum, unique
from typing import Final


@unique
class JobProgressErrorCode(StrEnum):
    COMPLETED_NOT_INTEGER = "completed_not_integer"
    COMPLETED_NEGATIVE = "completed_negative"
    TOTAL_NOT_INTEGER = "total_not_integer"
    TOTAL_NEGATIVE = "total_negative"


_MESSAGES: Final[dict[JobProgressErrorCode, str]] = {
    JobProgressErrorCode.COMPLETED_NOT_INTEGER: "completed must be an integer",
    JobProgressErrorCode.COMPLETED_NEGATIVE: "completed must be a non-negative integer",
    JobProgressErrorCode.TOTAL_NOT_INTEGER: "total must be an integer or None",
    JobProgressErrorCode.TOTAL_NEGATIVE: "total must be a non-negative integer",
}


class JobProgressTypeError(TypeError):
    """Invalid field type with a stable, machine-readable error code."""

    def __init__(self, code: JobProgressErrorCode) -> None:
        self.code = code
        super().__init__(_MESSAGES[code])


class JobProgressValueError(ValueError):
    """Invalid field value with a stable, machine-readable error code."""

    def __init__(self, code: JobProgressErrorCode) -> None:
        self.code = code
        super().__init__(_MESSAGES[code])
