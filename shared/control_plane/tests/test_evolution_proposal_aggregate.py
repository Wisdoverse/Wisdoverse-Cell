"""Unit tests for the EvolutionProposal aggregate (DDD-005)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.evolution_proposal import (
    EvolutionProposal,
    EvolutionRolloutStatusChanged,
    InvalidEvolutionRolloutTransitionError,
    TERMINAL_ROLLOUT_STATES,
    VALID_ROLLOUT_TRANSITIONS,
)
from shared.control_plane.models import (
    EvolutionProposal as EvolutionProposalRecord,
)
from shared.control_plane.models import EvolutionRolloutState, EvolutionTier


def _make_record(
    state: EvolutionRolloutState = EvolutionRolloutState.PROPOSED,
) -> EvolutionProposalRecord:
    return EvolutionProposalRecord(
        company_id="cmp_test",
        tier=EvolutionTier.L1,
        scope="agents/test",
        expected_benefit="improved latency",
        risk="low",
        rollout_state=state,
    )


def test_proposed_can_advance_to_shadow() -> None:
    aggregate = EvolutionProposal.from_record(_make_record())
    aggregate.advance_rollout(EvolutionRolloutState.SHADOW)
    assert aggregate.rollout_state == EvolutionRolloutState.SHADOW


def test_proposed_can_advance_to_canary() -> None:
    aggregate = EvolutionProposal.from_record(_make_record())
    aggregate.advance_rollout(EvolutionRolloutState.CANARY)
    assert aggregate.rollout_state == EvolutionRolloutState.CANARY


def test_proposed_can_advance_to_rejected() -> None:
    aggregate = EvolutionProposal.from_record(_make_record())
    aggregate.advance_rollout(EvolutionRolloutState.REJECTED)
    assert aggregate.rollout_state == EvolutionRolloutState.REJECTED


def test_proposed_cannot_advance_to_active_directly() -> None:
    aggregate = EvolutionProposal.from_record(_make_record())
    with pytest.raises(InvalidEvolutionRolloutTransitionError):
        aggregate.advance_rollout(EvolutionRolloutState.ACTIVE)


def test_canary_can_advance_to_active() -> None:
    aggregate = EvolutionProposal.from_record(
        _make_record(EvolutionRolloutState.CANARY)
    )
    aggregate.advance_rollout(EvolutionRolloutState.ACTIVE)
    assert aggregate.rollout_state == EvolutionRolloutState.ACTIVE


def test_shadow_can_roll_back() -> None:
    aggregate = EvolutionProposal.from_record(
        _make_record(EvolutionRolloutState.SHADOW)
    )
    aggregate.advance_rollout(EvolutionRolloutState.ROLLED_BACK)
    assert aggregate.rollout_state == EvolutionRolloutState.ROLLED_BACK


def test_active_can_roll_back() -> None:
    aggregate = EvolutionProposal.from_record(
        _make_record(EvolutionRolloutState.ACTIVE)
    )
    aggregate.advance_rollout(EvolutionRolloutState.ROLLED_BACK)
    assert aggregate.rollout_state == EvolutionRolloutState.ROLLED_BACK


def test_terminal_states_block_all_outgoing() -> None:
    for terminal in (
        EvolutionRolloutState.ROLLED_BACK,
        EvolutionRolloutState.REJECTED,
    ):
        aggregate = EvolutionProposal.from_record(_make_record(terminal))
        assert aggregate.is_terminal
        for target in EvolutionRolloutState:
            with pytest.raises(InvalidEvolutionRolloutTransitionError):
                aggregate.advance_rollout(target)


def test_transition_raises_typed_domain_event() -> None:
    aggregate = EvolutionProposal.from_record(_make_record())
    aggregate.advance_rollout(EvolutionRolloutState.SHADOW)
    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, EvolutionRolloutStatusChanged)
    assert event.from_state == EvolutionRolloutState.PROPOSED
    assert event.to_state == EvolutionRolloutState.SHADOW


def test_pull_events_clears_buffer() -> None:
    aggregate = EvolutionProposal.from_record(_make_record())
    aggregate.advance_rollout(EvolutionRolloutState.SHADOW)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_status_changed_event_is_frozen_value_object() -> None:
    event = EvolutionRolloutStatusChanged(
        proposal_id="ep_1",
        company_id="cmp_test",
        from_state=EvolutionRolloutState.PROPOSED,
        to_state=EvolutionRolloutState.SHADOW,
    )
    with pytest.raises(FrozenInstanceError):
        event.to_state = EvolutionRolloutState.CANARY  # type: ignore[misc]


def test_valid_rollout_transitions_table_covers_every_state() -> None:
    for state in EvolutionRolloutState:
        assert state in VALID_ROLLOUT_TRANSITIONS, f"missing FSM row for {state}"


def test_terminal_states_set_matches_empty_transition_rows() -> None:
    derived = {
        state
        for state, allowed in VALID_ROLLOUT_TRANSITIONS.items()
        if not allowed
    }
    assert TERMINAL_ROLLOUT_STATES == derived
