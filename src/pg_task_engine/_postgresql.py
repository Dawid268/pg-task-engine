"""Internal limits shared by validated models with PostgreSQL storage.

Keep these in sync with the types in the project's versioned SQL migrations.
"""

from datetime import timedelta

INT32_MAX = 2**31 - 1  # PostgreSQL INTEGER: signed 32-bit
INT64_MAX = 2**63 - 1  # PostgreSQL BIGINT: signed 64-bit
MAX_DURATION = timedelta(days=36_500)  # 100 years; safe for practical job deadlines


def require_utf8(value: str, *, field: str) -> None:
    """Reject unpaired Unicode surrogates before a PostgreSQL write.

    UTF-8 encoding validation does not replace the separate NUL check:
    NUL is valid UTF-8 but PostgreSQL TEXT and JSONB cannot store it.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field} must contain valid UTF-8 text") from error
