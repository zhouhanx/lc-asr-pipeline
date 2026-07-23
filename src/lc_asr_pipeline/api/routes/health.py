"""Liveness and readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from lc_asr_pipeline.api.dependencies import DatabaseDependency

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Report whether the API process can handle requests."""
    return HealthResponse(status="ok", service="api")


@router.get("/ready", response_model=HealthResponse)
async def readiness(database: DatabaseDependency) -> HealthResponse:
    """Report whether required PostgreSQL infrastructure is reachable."""
    if not await database.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is unavailable",
        )
    return HealthResponse(status="ok", service="postgresql")
