"""Ports for WebUI compatibility use cases."""

from typing import Any, Protocol


class WebUIControlPlaneQueryStore(Protocol):
    """Read-side port for WebUI control-plane compatibility views."""

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        search: str | None,
        limit: int,
    ) -> list[Any]:
        """Return agent roles for a company."""

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        """Return one agent role."""

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        agent_id: str | None = None,
        limit: int,
    ) -> list[Any]:
        """Return agent runs."""

    async def list_work_items(
        self,
        *,
        company_id: str,
        owner_agent_id: str | None = None,
        limit: int,
    ) -> list[Any]:
        """Return work items."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None,
        limit: int,
    ) -> list[Any]:
        """Return approval rows."""


class WebUIPromptConfigStore(Protocol):
    """Read/write port for WebUI agent prompt configuration."""

    async def get_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> dict[str, Any] | None:
        """Return an agent prompt config or None when the target is unknown."""

    async def update_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an agent prompt config or return None when the target is unknown."""
