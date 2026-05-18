"""Application use case for WebUI prompt-config compatibility writes."""

from typing import Any

from .webui_ports import WebUIPromptConfigStore


class WebUIPromptConfigUseCase:
    """Application use case for agent prompt-config reads and writes."""

    def __init__(
        self,
        *,
        store: WebUIPromptConfigStore,
        default_company_id: str,
    ):
        self._store = store
        self._default_company_id = default_company_id

    async def get_prompt_config(
        self,
        *,
        agent_id: str,
        company_id: str | None = None,
    ) -> dict[str, Any] | None:
        resolved_company_id = company_id or self._default_company_id
        return await self._store.get_prompt_config(
            company_id=resolved_company_id,
            agent_id=agent_id,
        )

    async def update_prompt_config(
        self,
        *,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any],
        company_id: str | None = None,
    ) -> dict[str, Any] | None:
        resolved_company_id = company_id or self._default_company_id
        return await self._store.update_prompt_config(
            company_id=resolved_company_id,
            agent_id=agent_id,
            system_prompt=system_prompt,
            updated_by=updated_by,
            metadata=metadata,
        )
