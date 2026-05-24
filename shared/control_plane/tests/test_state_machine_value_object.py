"""Tests for the Control Plane state-machine value object."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

import pytest

from shared.control_plane.domain.state_machine import (
    ControlPlaneStateMachine,
    InvalidControlPlaneStateMachineError,
)


class DemoState(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


def test_state_machine_normalizes_terminal_states_and_allowed_targets() -> None:
    machine = ControlPlaneStateMachine.from_transitions(
        {
            DemoState.DRAFT: {DemoState.ACTIVE, DemoState.CLOSED},
            DemoState.ACTIVE: {DemoState.CLOSED},
            DemoState.CLOSED: set(),
        }
    )

    assert isinstance(machine.transitions, MappingProxyType)
    assert machine.allowed_targets(DemoState.DRAFT) == frozenset(
        {DemoState.ACTIVE, DemoState.CLOSED}
    )
    assert machine.terminal_states == frozenset({DemoState.CLOSED})
    assert machine.is_terminal(DemoState.CLOSED)
    assert machine.can_transition(DemoState.ACTIVE, DemoState.CLOSED)


def test_state_machine_raises_caller_error_for_illegal_transition() -> None:
    machine = ControlPlaneStateMachine.from_transitions(
        {
            DemoState.DRAFT: {DemoState.ACTIVE},
            DemoState.ACTIVE: set(),
            DemoState.CLOSED: set(),
        }
    )

    with pytest.raises(ValueError, match="Demo demo_1: illegal transition active -> closed"):
        machine.ensure_can_transition(
            DemoState.ACTIVE,
            DemoState.CLOSED,
            subject="Demo demo_1",
            error_type=ValueError,
        )


def test_state_machine_requires_rows_for_all_targets() -> None:
    with pytest.raises(
        InvalidControlPlaneStateMachineError,
        match="missing_transition_rows:active",
    ):
        ControlPlaneStateMachine.from_transitions({DemoState.DRAFT: {DemoState.ACTIVE}})
