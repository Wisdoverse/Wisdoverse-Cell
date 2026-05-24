"""Tests for PJM decomposition value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agents.pjm_agent.core.domain.decomposition_values import DecompositionRejectionReason


def test_rejection_reason_is_trimmed_immutable_value_object() -> None:
    reason = DecompositionRejectionReason.from_text("  Split scope first  ")

    assert reason.text == "Split scope first"
    assert reason.length == len("Split scope first")
    assert reason.to_event_payload() == "Split scope first"
    with pytest.raises(FrozenInstanceError):
        reason.text = "changed"  # type: ignore[misc]


def test_rejection_reason_accepts_empty_input() -> None:
    assert DecompositionRejectionReason.from_text(None).text == ""
    assert DecompositionRejectionReason.from_text("").length == 0
