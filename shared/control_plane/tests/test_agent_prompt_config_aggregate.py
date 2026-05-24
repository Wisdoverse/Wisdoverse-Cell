"""Unit tests for the AgentPromptConfig aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.agent_prompt_config import (
    AGENT_PROMPT_MAX_LENGTH,
    AgentPromptConfig,
    AgentPromptConfigUpdated,
    InvalidAgentPromptConfigError,
    clean_system_prompt,
    clean_updated_by,
)
from shared.control_plane.models import AgentRunStatus


def test_prompt_config_update_normalizes_prompt_actor_and_metadata() -> None:
    aggregate = AgentPromptConfig.for_target(
        company_id="cmp_test",
        agent_id="requirement-manager",
    )

    aggregate.update(
        system_prompt="  Extract requirements.  ",
        updated_by="  human:pm  ",
        metadata={"source": "operator", "ticket": "REQ-1"},
    )

    assert aggregate.record.system_prompt == "Extract requirements."
    assert aggregate.record.updated_by == "human:pm"
    assert aggregate.record.metadata == {"source": "operator", "ticket": "REQ-1"}


def test_prompt_config_update_raises_pii_safe_domain_event() -> None:
    aggregate = AgentPromptConfig.for_target(
        company_id="cmp_test",
        agent_id="requirement-manager",
    )

    aggregate.update(
        system_prompt="Never include the raw prompt in the audit event.",
        updated_by="human:pm",
        metadata={"source": "operator"},
    )
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, AgentPromptConfigUpdated)
    assert event.prompt_length == len("Never include the raw prompt in the audit event.")
    assert event.metadata_keys == ("source",)
    assert "raw prompt" not in str(event.to_payload())


def test_pull_events_clears_buffer() -> None:
    aggregate = AgentPromptConfig.for_target(
        company_id="cmp_test",
        agent_id="requirement-manager",
    )
    aggregate.update(system_prompt="Prompt", updated_by="human:pm", metadata={})

    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_prompt_config_event_is_frozen_value_object() -> None:
    event = AgentPromptConfigUpdated(
        company_id="cmp_test",
        agent_id="requirement-manager",
        prompt_length=6,
        metadata_keys=("source",),
    )

    with pytest.raises(FrozenInstanceError):
        event.prompt_length = 7  # type: ignore[misc]


def test_prompt_config_cleaners_apply_domain_limits() -> None:
    assert clean_system_prompt("  prompt  ") == "prompt"
    assert clean_updated_by("  ") == "webui"
    assert clean_updated_by("x" * 200) == "x" * 128

    with pytest.raises(InvalidAgentPromptConfigError, match="system_prompt_too_long"):
        clean_system_prompt("x" * (AGENT_PROMPT_MAX_LENGTH + 1))


def test_prompt_config_metadata_uses_control_plane_value_object() -> None:
    aggregate = AgentPromptConfig.for_target(
        company_id="cmp_test",
        agent_id="requirement-manager",
    )

    aggregate.update(
        system_prompt="Prompt",
        updated_by="human:pm",
        metadata={" status ": AgentRunStatus.FAILED, "tags": ("urgent",)},
    )

    assert aggregate.record.metadata == {
        "status": "failed",
        "tags": ["urgent"],
    }
    assert aggregate.pull_events()[0].metadata_keys == ("status", "tags")
