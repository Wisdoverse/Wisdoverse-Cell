"""Agent wakeup adapter value objects for Control Plane runtime boundaries."""

from __future__ import annotations

import math
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .metadata import ControlPlaneMetadata

DEFAULT_AGENT_WAKEUP_ACTION = "wakeup"
DEFAULT_AGENT_WAKEUP_ADAPTER_TYPE = "builtin"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 300
MIN_HEARTBEAT_INTERVAL_SECONDS = 60


@dataclass(frozen=True, slots=True)
class AgentWakeupAdapterConfig:
    """Immutable interpretation of an AgentRole runtime adapter contract."""

    agent_id: str
    adapter_type: str = DEFAULT_AGENT_WAKEUP_ADAPTER_TYPE
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", str(self.agent_id))
        object.__setattr__(
            self,
            "adapter_type",
            str(self.adapter_type or DEFAULT_AGENT_WAKEUP_ADAPTER_TYPE),
        )
        object.__setattr__(
            self,
            "config",
            MappingProxyType(ControlPlaneMetadata.from_mapping(self.config).as_dict()),
        )

    @classmethod
    def from_agent_role(cls, agent: Any) -> AgentWakeupAdapterConfig:
        return cls(
            agent_id=agent.agent_id,
            adapter_type=getattr(
                agent,
                "adapter_type",
                DEFAULT_AGENT_WAKEUP_ADAPTER_TYPE,
            ),
            config=dict(getattr(agent, "adapter_config", None) or {}),
        )

    def action(self) -> Any:
        return self.config.get("action", DEFAULT_AGENT_WAKEUP_ACTION)

    def string_value(self, *keys: str) -> str | None:
        for key in keys:
            value = self.config.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def command(self) -> list[str]:
        command = self.config.get("command")
        if isinstance(command, str):
            return shlex.split(command)
        if isinstance(command, Sequence) and not isinstance(command, (bytes, bytearray)):
            return [str(part) for part in command if str(part)]
        return []

    def allowlist_key(self) -> str:
        configured = self.string_value("allowlist_key", "registry_key")
        return configured or f"{self.adapter_type}:{self.agent_id}"

    def heartbeat_enabled(self) -> bool:
        return self.config.get("heartbeat_enabled") is True

    def heartbeat_interval_seconds(self) -> int:
        raw = self.config.get(
            "heartbeat_interval_seconds",
            DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        )
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
        return max(value, MIN_HEARTBEAT_INTERVAL_SECONDS)

    def http_timeout_seconds(self) -> float:
        value = float(self.config.get("timeout_sec", 30))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid_executor_timeout")
        return min(value, 120.0)

    def process_timeout_seconds(self, *, max_seconds: int) -> int:
        value = int(self.config.get("timeout_sec", 300))
        if value <= 0:
            raise ValueError("invalid_executor_timeout")
        return min(value, max_seconds)


__all__ = [
    "AgentWakeupAdapterConfig",
    "DEFAULT_AGENT_WAKEUP_ACTION",
    "DEFAULT_AGENT_WAKEUP_ADAPTER_TYPE",
    "DEFAULT_HEARTBEAT_INTERVAL_SECONDS",
    "MIN_HEARTBEAT_INTERVAL_SECONDS",
]
