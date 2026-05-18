"""SQLAlchemy adapter for WebUI compatibility control-plane data."""

from typing import Any

from shared.control_plane.agent_prompt_config import (
    get_or_default_prompt_config,
    update_prompt_config_with_audit,
)
from shared.control_plane.agent_registry_store import (
    SqlAlchemyControlPlaneAgentRegistryStore,
)
from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.prompt_config_store import SqlAlchemyControlPlanePromptConfigStore
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore

from ..core.webui_ports import WebUIControlPlaneQueryStore, WebUIPromptConfigStore


class SqlAlchemyWebUIControlPlaneStore(
    WebUIControlPlaneQueryStore,
    WebUIPromptConfigStore,
):
    """Control-plane repository adapter for WebUI compatibility use cases."""

    def __init__(self, db_manager):
        self._db_manager = db_manager

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        search: str | None,
        limit: int,
    ) -> list[Any]:
        async with self._db_manager.session() as session:
            return await SqlAlchemyControlPlaneAgentRegistryStore(
                session
            ).list_agent_roles(
                company_id=company_id,
                search=search,
                limit=limit,
            )

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        async with self._db_manager.session() as session:
            return await SqlAlchemyControlPlaneAgentRegistryStore(session).get_agent_role(
                company_id=company_id,
                agent_id=agent_id,
            )

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        agent_id: str | None = None,
        limit: int,
    ) -> list[Any]:
        async with self._db_manager.session() as session:
            return await SqlAlchemyControlPlaneAgentRunStore(session).list_agent_runs(
                company_id=company_id,
                agent_id=agent_id,
                limit=limit,
            )

    async def list_work_items(
        self,
        *,
        company_id: str,
        owner_agent_id: str | None = None,
        limit: int,
    ) -> list[Any]:
        async with self._db_manager.session() as session:
            return await SqlAlchemyControlPlaneWorkItemStore(session).list_work_items(
                company_id=company_id,
                owner_agent_id=owner_agent_id,
                limit=limit,
            )

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None,
        limit: int,
    ) -> list[Any]:
        async with self._db_manager.session() as session:
            return await SqlAlchemyControlPlaneApprovalStore(session).list_approvals(
                company_id=company_id,
                status=status,
                limit=limit,
            )

    async def get_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> dict[str, Any] | None:
        async with self._db_manager.session() as session:
            store = SqlAlchemyControlPlanePromptConfigStore(session)
            try:
                return await get_or_default_prompt_config(
                    store,
                    company_id=company_id,
                    agent_id=agent_id,
                )
            except KeyError:
                return None

    async def update_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self._db_manager.session() as session:
            store = SqlAlchemyControlPlanePromptConfigStore(session)
            try:
                return await update_prompt_config_with_audit(
                    store,
                    company_id=company_id,
                    agent_id=agent_id,
                    system_prompt=system_prompt,
                    updated_by=updated_by,
                    metadata=metadata,
                )
            except KeyError:
                return None
