"""DSAR (Data Subject Access Request) schemas.

Pydantic v2 models for GDPR Art. 17/20 and China PIPL Art. 47 compliance.
"""
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DSARRequest(BaseModel):
    """Inbound DSAR request body."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., min_length=1, description="User open_id")


class DSARResult(BaseModel):
    """Structured result of a DSAR operation."""

    user_id: str
    action: Literal["export", "delete", "delete_dry_run"]
    affected_tables: dict[str, int] = Field(
        default_factory=dict,
        description="table_name -> record_count",
    )
    redis_keys_affected: int = 0
    status: Literal["completed", "partial_failure"] = "completed"
    errors: list[str] = Field(default_factory=list)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
