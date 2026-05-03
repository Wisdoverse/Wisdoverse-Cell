"""Tests for coordinator prompt contract references."""

from services.orchestration.coordinator.core.prompts import build_system_prompt
from shared.schemas.event import EventTypes


def test_system_prompt_uses_canonical_event_names() -> None:
    prompt = build_system_prompt()

    assert EventTypes.PM_PRD_READY in prompt
    assert "pm.prd_ready" not in prompt
