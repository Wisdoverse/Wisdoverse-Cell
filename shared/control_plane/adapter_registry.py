"""Adapter registry and safety policy for control-plane agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AdapterKind = Literal["builtin", "http", "local"]


@dataclass(frozen=True)
class AdapterDefinition:
    adapter_type: str
    kind: AdapterKind
    description: str


class AdapterRegistry:
    """Known adapter types for persisted AgentRole definitions."""

    def __init__(self, definitions: list[AdapterDefinition]) -> None:
        self._definitions = {
            definition.adapter_type: definition for definition in definitions
        }

    @classmethod
    def default(cls) -> "AdapterRegistry":
        return cls(
            [
                AdapterDefinition(
                    adapter_type="builtin",
                    kind="builtin",
                    description="Record wakeups for built-in deployed agents.",
                ),
                AdapterDefinition(
                    adapter_type="http",
                    kind="http",
                    description="Call a deployed agent request boundary over HTTP.",
                ),
                AdapterDefinition(
                    adapter_type="process",
                    kind="local",
                    description="Run an operator-reviewed local process command.",
                ),
                AdapterDefinition(
                    adapter_type="codex_local",
                    kind="local",
                    description="Run a local Codex command through the process adapter.",
                ),
                AdapterDefinition(
                    adapter_type="claude_local",
                    kind="local",
                    description="Run a local Claude command through the process adapter.",
                ),
            ]
        )

    def get(self, adapter_type: str) -> AdapterDefinition | None:
        return self._definitions.get(adapter_type)

    def is_registered(self, adapter_type: str) -> bool:
        return adapter_type in self._definitions

    def is_local(self, adapter_type: str) -> bool:
        definition = self.get(adapter_type)
        return definition is not None and definition.kind == "local"


DEFAULT_ADAPTER_REGISTRY = AdapterRegistry.default()
