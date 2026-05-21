"""Serialization helpers for Control Plane HTTP adapters."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, BaseModel):
        return row.model_dump(mode="json")

    data: dict[str, Any] = {}
    for attr_ref in row.__mapper__.column_attrs:
        attr = attr_ref.key
        key = "metadata" if attr == "metadata_json" else attr
        data[key] = serialize_value(getattr(row, attr))
    return data
