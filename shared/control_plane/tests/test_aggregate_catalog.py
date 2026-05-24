"""Unit tests for the Control Plane aggregate catalog."""

from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from shared.control_plane import models
from shared.control_plane.domain.aggregate_catalog import (
    CONTROL_PLANE_AGGREGATES,
    ControlPlaneAggregateDefinition,
    aggregate_module_paths,
    aggregate_record_names,
    aggregate_test_paths,
)

EXPECTED_RECORD_NAMES = (
    "CompanyContext",
    "Goal",
    "AgentRole",
    "WorkItem",
    "AgentRun",
    "Decision",
    "ApprovalRequest",
    "BudgetPolicy",
    "BudgetUsage",
    "Artifact",
    "AuditEvent",
    "EvolutionProposal",
    "AgentPromptConfig",
)


def _module_name_from_path(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".")


def test_control_plane_aggregate_catalog_is_complete() -> None:
    """The catalog is the canonical inventory of Control Plane aggregates."""
    assert aggregate_record_names() == EXPECTED_RECORD_NAMES
    assert len(CONTROL_PLANE_AGGREGATES) == 13
    assert len(set(aggregate_record_names())) == len(EXPECTED_RECORD_NAMES)
    assert len(set(aggregate_module_paths())) == len(EXPECTED_RECORD_NAMES)
    assert len(set(aggregate_test_paths())) == len(EXPECTED_RECORD_NAMES)


def test_control_plane_aggregate_catalog_points_to_existing_code() -> None:
    """Each catalog entry must point to an aggregate module and unit test."""
    for definition in CONTROL_PLANE_AGGREGATES:
        module_path = Path(definition.module_path)
        test_path = Path(definition.test_path)

        assert module_path.exists(), f"missing aggregate module: {module_path}"
        assert test_path.exists(), f"missing aggregate test: {test_path}"

        module = importlib.import_module(_module_name_from_path(definition.module_path))
        assert hasattr(module, definition.aggregate_name), (
            f"{definition.module_path} does not export "
            f"{definition.aggregate_name}"
        )
        assert hasattr(models, definition.record_name), (
            f"shared.control_plane.models does not export "
            f"{definition.record_name}"
        )


def test_control_plane_aggregate_definitions_are_immutable() -> None:
    """Catalog entries are value objects, not mutable runtime settings."""
    definition = CONTROL_PLANE_AGGREGATES[0]

    with pytest.raises(FrozenInstanceError):
        definition.aggregate_name = "Other"  # type: ignore[misc]


def test_control_plane_aggregate_definition_rejects_invalid_paths() -> None:
    """Architecture metadata should remain repo-relative and POSIX-shaped."""
    with pytest.raises(ValueError):
        ControlPlaneAggregateDefinition(
            aggregate_name="Goal",
            record_name="Goal",
            module_path="/shared/control_plane/domain/goal.py",
            test_path="shared/control_plane/tests/test_goal_aggregate.py",
        )

    with pytest.raises(ValueError):
        ControlPlaneAggregateDefinition(
            aggregate_name="Goal",
            record_name="Goal",
            module_path="shared\\control_plane\\domain\\goal.py",
            test_path="shared/control_plane/tests/test_goal_aggregate.py",
        )
