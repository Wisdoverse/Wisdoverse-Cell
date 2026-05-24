"""AgentPromptConfig aggregate and prompt-update policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import AgentPromptConfig as AgentPromptConfigRecord
from .events import ControlPlaneDomainEvent
from .metadata import ControlPlaneMetadata

AGENT_PROMPT_MAX_LENGTH = 50_000
AGENT_PROMPT_UPDATED_BY_MAX_LENGTH = 128


class InvalidAgentPromptConfigError(ValueError):
    """Raised when a prompt-config update violates domain policy."""


def clean_system_prompt(value: Any) -> str:
    """Normalize and validate a persisted agent system prompt."""
    prompt = str(value or "").strip()
    if len(prompt) > AGENT_PROMPT_MAX_LENGTH:
        raise InvalidAgentPromptConfigError("system_prompt_too_long")
    return prompt


def clean_updated_by(value: Any) -> str:
    """Normalize the actor recorded for a prompt-config update."""
    return str(value or "webui").strip()[:AGENT_PROMPT_UPDATED_BY_MAX_LENGTH] or "webui"


@dataclass(frozen=True, slots=True)
class AgentPromptConfigUpdated(ControlPlaneDomainEvent):
    """PII-safe in-memory event raised when prompt configuration changes."""

    company_id: str
    agent_id: str
    prompt_length: int
    metadata_keys: tuple[str, ...]


@dataclass
class AgentPromptConfig:
    """AgentPromptConfig aggregate for system-prompt override policy."""

    record: AgentPromptConfigRecord
    _events: list[AgentPromptConfigUpdated] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: AgentPromptConfigRecord) -> AgentPromptConfig:
        return cls(record=record)

    @classmethod
    def for_target(
        cls,
        *,
        company_id: str,
        agent_id: str,
        existing: AgentPromptConfigRecord | None = None,
    ) -> AgentPromptConfig:
        if existing is not None:
            return cls.from_record(existing)
        return cls(
            record=AgentPromptConfigRecord(
                company_id=company_id,
                agent_id=agent_id,
            )
        )

    @property
    def company_id(self) -> str:
        return self.record.company_id

    @property
    def agent_id(self) -> str:
        return self.record.agent_id

    def update(
        self,
        *,
        system_prompt: Any,
        updated_by: Any,
        metadata: dict[str, Any] | None,
    ) -> None:
        prompt = clean_system_prompt(system_prompt)
        actor = clean_updated_by(updated_by)
        clean_metadata = ControlPlaneMetadata.from_mapping(metadata).as_dict()
        self.record = self.record.model_copy(
            update={
                "system_prompt": prompt,
                "updated_by": actor,
                "metadata": clean_metadata,
            }
        )
        self._events.append(
            AgentPromptConfigUpdated(
                company_id=self.company_id,
                agent_id=self.agent_id,
                prompt_length=len(prompt),
                metadata_keys=ControlPlaneMetadata.from_mapping(
                    clean_metadata
                ).keys_tuple,
            )
        )

    def pull_events(self) -> list[AgentPromptConfigUpdated]:
        """Drain raised domain events for audit/outbox collection."""
        drained = list(self._events)
        self._events.clear()
        return drained


__all__ = [
    "AGENT_PROMPT_MAX_LENGTH",
    "AGENT_PROMPT_UPDATED_BY_MAX_LENGTH",
    "AgentPromptConfig",
    "AgentPromptConfigUpdated",
    "InvalidAgentPromptConfigError",
    "clean_system_prompt",
    "clean_updated_by",
]
