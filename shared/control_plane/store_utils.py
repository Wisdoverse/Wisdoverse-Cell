"""Shared helpers for control-plane SQLAlchemy store adapters."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


def now_utc() -> datetime:
    """Return the current UTC timestamp for persistence updates."""
    return datetime.now(UTC)


def to_db_value(value: Any) -> Any:
    """Normalize Pydantic values into SQLAlchemy JSON/scalar values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [to_db_value(item) for item in value]
    if isinstance(value, dict):
        return {key: to_db_value(item) for key, item in value.items()}
    return value


def model_values(model: BaseModel) -> dict[str, Any]:
    """Return SQLAlchemy constructor values for a control-plane model."""
    data = model.model_dump(mode="python")
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        db_key = "metadata_json" if key == "metadata" else key
        normalized[db_key] = to_db_value(value)
    return normalized
