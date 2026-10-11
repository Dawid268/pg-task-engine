"""Public diagnostic routes only; queue functionality is not implemented yet."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from pg_task_engine import __version__

router = APIRouter()


class LivenessResponse(BaseModel):
    """This process responds to HTTP; no database or worker readiness is implied."""

    status: Literal["alive"] = "alive"


@router.get("/version", tags=["version"])
async def version() -> str:
    """Return the library version, matching the source boilerplate's response shape."""
    return __version__


@router.get("/health/live", tags=["health"])
async def liveness() -> LivenessResponse:
    """Report HTTP liveness without pretending that a queue already exists."""
    return LivenessResponse()
