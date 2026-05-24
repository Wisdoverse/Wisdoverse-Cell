"""Tests for the Control Plane metadata value object."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from shared.control_plane.domain.metadata import (
    ControlPlaneMetadata,
    InvalidControlPlaneMetadataError,
)
from shared.control_plane.models import AgentRunStatus


def test_metadata_normalizes_json_friendly_values() -> None:
    metadata = ControlPlaneMetadata.from_mapping(
        {
            " status ": AgentRunStatus.SUCCEEDED,
            "at": datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
            "tags": {"b", "a"},
            "nested": {" retry ": (1, AgentRunStatus.FAILED)},
        }
    )

    assert metadata.keys_tuple == ("at", "nested", "status", "tags")
    assert metadata.as_dict() == {
        "status": "succeeded",
        "at": "2026-05-23T12:00:00+00:00",
        "tags": ["a", "b"],
        "nested": {"retry": [1, "failed"]},
    }


def test_metadata_is_immutable_at_the_boundary() -> None:
    metadata = ControlPlaneMetadata.from_mapping({"source": "operator"})

    assert isinstance(metadata.values, MappingProxyType)
    with pytest.raises(TypeError):
        metadata.values["source"] = "system"  # type: ignore[index]


def test_metadata_rejects_blank_keys() -> None:
    with pytest.raises(InvalidControlPlaneMetadataError, match="metadata_key_required"):
        ControlPlaneMetadata.from_mapping({" ": "invalid"})
