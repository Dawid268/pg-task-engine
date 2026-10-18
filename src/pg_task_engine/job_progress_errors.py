"""Stable validation error codes for JobProgress.

Callers should branch on an error code, not on the human-readable message.
"""

from enum import StrEnum, unique
from typing import Final


@unique
class JobProgressErrorCode(StrEnum):
    COMPLETED_NOT_INTEGER = "completed_not_integer"
    COMPLETED_NEGATIVE = "completed_negative"
    COMPLETED_EXCEEDS_TOTAL = "completed_exceeds_total"
    COMPLETED_OUT_OF_RANGE = "completed_out_of_range"
    TOTAL_NOT_INTEGER = "total_not_integer"
    TOTAL_NEGATIVE = "total_negative"
    TOTAL_OUT_OF_RANGE = "total_out_of_range"
    REVISION_NOT_INTEGER = "revision_not_integer"
    REVISION_NEGATIVE = "revision_negative"
    REVISION_OUT_OF_RANGE = "revision_out_of_range"
    UNIT_TYPE_ERROR = "unit_type_error"
    UNIT_EMPTY = "unit_empty"
    UNIT_CONTAINS_NUL = "unit_contains_nul"
    UNIT_INVALID_UNICODE = "unit_invalid_unicode"
    UPDATED_AT_TYPE_ERROR = "updated_at_type_error"
    UPDATED_AT_NAIVE = "updated_at_naive"
    UPDATED_AT_NOT_UTC = "updated_at_not_utc"


_MESSAGES: Final[dict[JobProgressErrorCode, str]] = {
    JobProgressErrorCode.COMPLETED_NOT_INTEGER: "completed must be an integer",
    JobProgressErrorCode.COMPLETED_NEGATIVE: "completed must be a non-negative integer",
    JobProgressErrorCode.COMPLETED_EXCEEDS_TOTAL: "completed must not exceed total",
    JobProgressErrorCode.COMPLETED_OUT_OF_RANGE: "completed exceeds PostgreSQL INTEGER range",
    JobProgressErrorCode.TOTAL_NOT_INTEGER: "total must be an integer or None",
    JobProgressErrorCode.TOTAL_NEGATIVE: "total must be a non-negative integer",
    JobProgressErrorCode.TOTAL_OUT_OF_RANGE: "total exceeds PostgreSQL INTEGER range",
    JobProgressErrorCode.REVISION_NOT_INTEGER: "revision must be an integer",
    JobProgressErrorCode.REVISION_NEGATIVE: "revision must be a non-negative integer",
    JobProgressErrorCode.REVISION_OUT_OF_RANGE: "revision exceeds PostgreSQL BIGINT range",
    JobProgressErrorCode.UNIT_TYPE_ERROR: "unit must be a string",
    JobProgressErrorCode.UNIT_EMPTY: "unit must not be empty",
    JobProgressErrorCode.UNIT_CONTAINS_NUL: "unit must not contain NUL characters",
    JobProgressErrorCode.UNIT_INVALID_UNICODE: "unit must contain valid UTF-8 text",
    JobProgressErrorCode.UPDATED_AT_TYPE_ERROR: "updated_at must be a datetime",
    JobProgressErrorCode.UPDATED_AT_NAIVE: "updated_at must be timezone-aware",
    JobProgressErrorCode.UPDATED_AT_NOT_UTC: "updated_at must be in UTC",
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
