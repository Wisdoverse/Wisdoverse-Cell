"""Ports for control-plane agent prompt configuration."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AuditEvent, CompanyContext


class ControlPlanePromptConfigStore(Protocol):
    """Read-side persistence required by prompt-configuration helpers."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        """Return an agent role if the target exists."""

    async def get_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        """Return a stored prompt configuration if present."""

    async def upsert_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Create or update one prompt configuration."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
