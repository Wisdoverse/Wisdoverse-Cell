"""Unified error response model."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str
    trace_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: dict | None = None
