"""Control Plane metadata value objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any


class InvalidControlPlaneMetadataError(ValueError):
    """Raised when Control Plane metadata cannot be normalized."""


@dataclass(frozen=True, slots=True)
class ControlPlaneMetadata:
    """Immutable JSON-friendly metadata map for Control Plane records."""

    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "values",
            MappingProxyType(_freeze_metadata_mapping(self.values)),
        )

    @classmethod
    def empty(cls) -> ControlPlaneMetadata:
        return cls({})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> ControlPlaneMetadata:
        return cls(dict(value or {}))

    @property
    def keys_tuple(self) -> tuple[str, ...]:
        return tuple(sorted(self.values))

    def as_dict(self) -> dict[str, Any]:
        return {key: _unfreeze_metadata_value(value) for key, value in self.values.items()}


def _freeze_metadata_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    return {
        _clean_metadata_key(key): _freeze_metadata_value(item)
        for key, item in dict(value or {}).items()
    }


def _clean_metadata_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        raise InvalidControlPlaneMetadataError("metadata_key_required")
    return key


def _freeze_metadata_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return MappingProxyType(_freeze_metadata_mapping(value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_metadata_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze_metadata_value(item) for item in sorted(value, key=str))
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _unfreeze_metadata_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _unfreeze_metadata_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze_metadata_value(item) for item in value]
    return value


__all__ = [
    "ControlPlaneMetadata",
    "InvalidControlPlaneMetadataError",
]
