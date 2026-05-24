"""Agent registry and operation HTTP routes for the Control Plane API."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.api import raise_control_plane_api_error
from shared.middleware.internal_auth import verify_internal_key

from ..agent_operation_use_cases import (
    AgentDefinitionNotFoundError,
    AgentOperationCompanyNotFoundError,
    wake_agent_definition,
)
from ..agent_operation_use_cases import (
    run_heartbeat_scheduler_once as run_heartbeat_scheduler_once_from_store,
)
from ..agent_prompt_config import (
    AGENT_PROMPT_MAX_LENGTH,
    clean_system_prompt,
    clean_updated_by,
    get_or_default_prompt_config,
    update_prompt_config_with_audit,
)
from ..agent_registry_use_cases import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    UnsupportedAdapterTypeError,
    create_agent_role_with_audit,
    update_agent_role_with_audit,
    update_agent_status_with_audit,
)
from ..agent_registry_use_cases import get_agent_role as get_agent_role_from_registry
from ..agent_registry_use_cases import list_agent_roles as list_agent_roles_from_registry
from ..agent_runner import AgentWakeupError
from ..api_serialization import row_to_dict
from ..domain.agent_role import InvalidAgentRoleStatusError, InvalidAgentRoleTransitionError
from ..models import AgentInteractionMode, AgentKind, AgentRole
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import (
    CompanyResolver,
    StoresDependency,
    UnitOfWorkDependency,
    clean_string_list,
)


class AgentDefinitionCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    agent_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    display_name: str = Field(min_length=1, max_length=128)
    agent_kind: AgentKind = AgentKind.ORGANIZATION_ROLE
    interaction_mode: AgentInteractionMode = AgentInteractionMode.ROUTED
    role: str = Field(default="worker", min_length=1, max_length=64)
    title: str = Field(default="", max_length=128)
    domain: str = Field(default="operations", max_length=64)
    reports_to_agent_id: str | None = Field(default=None, max_length=64)
    adapter_type: str = Field(default="builtin", min_length=1, max_length=64)
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    context_sources: list[str] = Field(default_factory=list, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    responsibilities: list[str] = Field(default_factory=list, max_length=50)
    subscribed_events: list[str] = Field(default_factory=list, max_length=100)
    published_events: list[str] = Field(default_factory=list, max_length=100)
    permissions: list[str] = Field(default_factory=list, max_length=50)
    budget_policy_id: str | None = Field(default=None, max_length=48)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active", min_length=1, max_length=32)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "capabilities",
        "context_sources",
        "responsibilities",
        "subscribed_events",
        "published_events",
        "permissions",
        mode="before",
    )
    @classmethod
    def _clean_list(cls, value: Any) -> list[str]:
        return clean_string_list(value)

    @field_validator(
        "display_name",
        "role",
        "title",
        "domain",
        "adapter_type",
        "created_by",
        mode="before",
    )
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _validate_agent_contract(self) -> "AgentDefinitionCreateRequest":
        if (
            self.agent_kind
            not in {AgentKind.ORGANIZATION_ROLE, AgentKind.INTEGRATION_GATEWAY}
            and self.interaction_mode == AgentInteractionMode.DIRECT
        ):
            raise ValueError(
                "only organization_role or integration_gateway agents may use direct interaction"
            )
        if self.agent_kind == AgentKind.ORGANIZATION_ROLE and not self.context_sources:
            self.context_sources = ["control_plane"]
        return self

    @field_validator("reports_to_agent_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class AgentStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)
    actor_id: str = Field(default="api", min_length=1, max_length=128)


class AgentPromptConfigUpdateRequest(BaseModel):
    system_prompt: str = Field(default="", max_length=AGENT_PROMPT_MAX_LENGTH)
    updated_by: str = Field(default="webui", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def _clean_system_prompt(cls, value: Any) -> str:
        return clean_system_prompt(value)

    @field_validator("updated_by", mode="before")
    @classmethod
    def _clean_updated_by(cls, value: Any) -> str:
        return clean_updated_by(value)


class AgentWakeupRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    input: dict[str, Any] = Field(default_factory=dict)
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, max_length=96)
    goal_id: str | None = Field(default=None, max_length=48)
    work_item_id: str | None = Field(default=None, max_length=48)


class HeartbeatRunRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    limit: int = Field(default=500, ge=1, le=500)


def create_agent_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/agents")
    async def list_agents(
        company_id: str | None = None,
        status: str | None = None,
        agent_kind: AgentKind | None = None,
        interaction_mode: AgentInteractionMode | None = None,
        adapter_type: str | None = None,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.agent_registry
        rows = await list_agent_roles_from_registry(
            store,
            company_id=resolve_company(company_id),
            status=status,
            agent_kind=agent_kind.value if agent_kind else None,
            interaction_mode=interaction_mode.value if interaction_mode else None,
            adapter_type=adapter_type,
            search=search,
            limit=limit,
        )
        return {"agents": [row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/agents",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_agent(
        body: AgentDefinitionCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.agent_registry
        company_id = resolve_company(body.company_id)
        try:
            row = await create_agent_role_with_audit(
                store,
                AgentRole(
                    company_id=company_id,
                    agent_id=body.agent_id,
                    display_name=body.display_name,
                    agent_kind=body.agent_kind,
                    interaction_mode=body.interaction_mode,
                    role=body.role,
                    title=body.title,
                    domain=body.domain,
                    reports_to_agent_id=body.reports_to_agent_id,
                    adapter_type=body.adapter_type,
                    adapter_config=body.adapter_config,
                    context_sources=body.context_sources,
                    capabilities=body.capabilities,
                    responsibilities=body.responsibilities,
                    subscribed_events=body.subscribed_events,
                    published_events=body.published_events,
                    permissions=body.permissions,
                    budget_policy_id=body.budget_policy_id,
                    escalation_policy=body.escalation_policy,
                    status=body.status,
                    created_by=body.created_by,
                    metadata=body.metadata,
                ),
            )
        except AgentAlreadyExistsError:
            raise_control_plane_api_error(status_code=409, detail="agent_already_exists")
        except UnsupportedAdapterTypeError:
            raise_control_plane_api_error(status_code=400, detail="unsupported_adapter_type")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/agents/{agent_id}")
    async def get_agent(
        agent_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.agent_registry
        try:
            row = await get_agent_role_from_registry(
                store,
                company_id=resolve_company(company_id),
                agent_id=agent_id,
            )
        except AgentNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        return row_to_dict(row)

    @router.put("/agents/{agent_id}")
    async def update_agent(
        agent_id: str,
        body: AgentDefinitionCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        if body.agent_id != agent_id:
            raise_control_plane_api_error(status_code=400, detail="agent_id_mismatch")

        stores = uow.stores
        store = stores.agent_registry
        company_id = resolve_company(body.company_id)
        try:
            row = await update_agent_role_with_audit(
                store,
                AgentRole(
                    company_id=company_id,
                    agent_id=agent_id,
                    display_name=body.display_name,
                    agent_kind=body.agent_kind,
                    interaction_mode=body.interaction_mode,
                    role=body.role,
                    title=body.title,
                    domain=body.domain,
                    reports_to_agent_id=body.reports_to_agent_id,
                    adapter_type=body.adapter_type,
                    adapter_config=body.adapter_config,
                    context_sources=body.context_sources,
                    capabilities=body.capabilities,
                    responsibilities=body.responsibilities,
                    subscribed_events=body.subscribed_events,
                    published_events=body.published_events,
                    permissions=body.permissions,
                    budget_policy_id=body.budget_policy_id,
                    escalation_policy=body.escalation_policy,
                    created_by=body.created_by,
                    metadata=body.metadata,
                ),
            )
        except UnsupportedAdapterTypeError:
            raise_control_plane_api_error(status_code=400, detail="unsupported_adapter_type")
        except AgentNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        except InvalidAgentRoleStatusError:
            raise_control_plane_api_error(status_code=400, detail="invalid_agent_status")
        except InvalidAgentRoleTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_agent_status_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    @router.get("/agents/{agent_id}/prompt-config")
    async def get_agent_prompt_config(
        agent_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.prompt_configs
        resolved_company_id = resolve_company(company_id)
        try:
            return await get_or_default_prompt_config(
                store,
                company_id=resolved_company_id,
                agent_id=agent_id,
            )
        except KeyError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")

    @router.put("/agents/{agent_id}/prompt-config")
    async def update_agent_prompt_config(
        agent_id: str,
        body: AgentPromptConfigUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.prompt_configs
        resolved_company_id = resolve_company(company_id)
        try:
            result = await update_prompt_config_with_audit(
                store,
                company_id=resolved_company_id,
                agent_id=agent_id,
                system_prompt=body.system_prompt,
                updated_by=body.updated_by,
                metadata=body.metadata,
            )
        except KeyError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        await uow.commit()
        return result

    @router.patch("/agents/{agent_id}/status")
    async def update_agent_status(
        agent_id: str,
        body: AgentStatusUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.agent_registry
        resolved_company_id = resolve_company(company_id)
        try:
            row = await update_agent_status_with_audit(
                store,
                company_id=resolved_company_id,
                agent_id=agent_id,
                status=body.status,
                actor_id=body.actor_id,
            )
        except AgentNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        await uow.commit()
        return row_to_dict(row)

    @router.post("/agents/{agent_id}/wake", dependencies=[Depends(verify_internal_key)])
    async def wake_agent(
        agent_id: str,
        body: AgentWakeupRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.agent_operations
        try:
            result = await wake_agent_definition(
                store,
                company_id=resolve_company(body.company_id),
                agent_id=agent_id,
                input_payload=body.input,
                actor_id=body.actor_id,
                trace_id=body.trace_id,
                goal_id=body.goal_id,
                work_item_id=body.work_item_id,
            )
        except AgentDefinitionNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        except AgentWakeupError as exc:
            await uow.commit()
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.detail)

        await uow.commit()
        return {
            "run": (
                row_to_dict(result.run)
                if result.run is not None
                else {"run_id": result.wakeup.run_id}
            ),
            "output": result.wakeup.output,
            "evidence_artifact_id": result.wakeup.evidence_artifact_id,
        }

    @router.post(
        "/scheduler/heartbeats/run-once",
        dependencies=[Depends(verify_internal_key)],
    )
    async def run_heartbeat_scheduler_once(
        body: HeartbeatRunRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.agent_operations
        company_id = resolve_company(body.company_id)
        try:
            results = await run_heartbeat_scheduler_once_from_store(
                store,
                company_id=company_id,
                limit=body.limit,
            )
        except AgentOperationCompanyNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="company_not_found")
        await uow.commit()
        return {
            "company_id": company_id,
            "results": [asdict(item) for item in results],
            "total": len(results),
        }

    return router
