"""Unit tests for Control Plane agent wakeup adapter value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from shared.control_plane.domain.agent_wakeup_adapter import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    MIN_HEARTBEAT_INTERVAL_SECONDS,
    AgentWakeupAdapterConfig,
)


def test_adapter_config_normalizes_agent_role_fields() -> None:
    adapter = AgentWakeupAdapterConfig.from_agent_role(
        SimpleNamespace(
            agent_id="ops-runner",
            adapter_type="process",
            adapter_config={
                "action": "execute",
                "allowlist_key": "reviewed:ops-runner",
                "base_url": "  http://agent.test  ",
            },
        )
    )

    assert adapter.agent_id == "ops-runner"
    assert adapter.adapter_type == "process"
    assert adapter.action() == "execute"
    assert adapter.allowlist_key() == "reviewed:ops-runner"
    assert adapter.string_value("url", "base_url") == "http://agent.test"


def test_adapter_config_is_immutable_value_object() -> None:
    adapter = AgentWakeupAdapterConfig(
        agent_id="ops-runner",
        config={"base_url": "http://agent.test"},
    )

    with pytest.raises(FrozenInstanceError):
        adapter.agent_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        adapter.config["base_url"] = "http://other.test"  # type: ignore[index]


def test_adapter_config_derives_command_and_allowlist_key() -> None:
    string_command = AgentWakeupAdapterConfig(
        agent_id="ops-runner",
        adapter_type="codex_local",
        config={"command": "python -m worker --flag"},
    )
    list_command = AgentWakeupAdapterConfig(
        agent_id="ops-runner",
        adapter_type="process",
        config={"command": ["python", "", "-m", "worker"]},
    )
    registry_key = AgentWakeupAdapterConfig(
        agent_id="ops-runner",
        adapter_type="process",
        config={"registry_key": "reviewed:process:ops"},
    )

    assert string_command.command() == ["python", "-m", "worker", "--flag"]
    assert list_command.command() == ["python", "-m", "worker"]
    assert list_command.allowlist_key() == "process:ops-runner"
    assert registry_key.allowlist_key() == "reviewed:process:ops"


def test_adapter_config_owns_heartbeat_interval_policy() -> None:
    enabled = AgentWakeupAdapterConfig(
        agent_id="ops-runner",
        config={"heartbeat_enabled": True, "heartbeat_interval_seconds": 10},
    )
    invalid_interval = AgentWakeupAdapterConfig(
        agent_id="ops-runner",
        config={"heartbeat_enabled": False, "heartbeat_interval_seconds": "bad"},
    )

    assert enabled.heartbeat_enabled() is True
    assert enabled.heartbeat_interval_seconds() == MIN_HEARTBEAT_INTERVAL_SECONDS
    assert invalid_interval.heartbeat_enabled() is False
    assert (
        invalid_interval.heartbeat_interval_seconds()
        == DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    )
