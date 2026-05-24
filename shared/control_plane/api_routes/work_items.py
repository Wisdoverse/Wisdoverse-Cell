"""Work Item HTTP routes for the Control Plane API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator

from shared.api import raise_control_plane_api_error

from ..agent_operation_use_cases import AgentDefinitionNotFoundError
from ..agent_runner import AgentWakeupError
from ..api_serialization import row_to_dict, serialize_value
from ..audit_timeline_use_cases import (
    build_work_item_activity as build_work_item_activity_from_store,
)
from ..domain.work_item import InvalidWorkItemTransitionError
from ..models import WorkItem, WorkItemPriority, WorkItemStatus
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from ..work_item_execution_use_cases import (
    WorkItemExecutionAgentRequiredError,
    run_work_item_with_agent,
)
from ..work_item_operation_use_cases import (
    WorkItemAssigneeRequiredError,
    WorkItemCloseStatusError,
    block_work_item,
    close_work_item,
    reassign_work_item,
)
from ..work_item_use_cases import (
    WorkItemDependencyNotFoundError,
    WorkItemGoalNotFoundError,
    WorkItemNotFoundError,
    create_work_item_with_audit,
    update_work_item_status_with_audit,
)
from ..work_item_use_cases import get_work_item as get_work_item_from_store
from ..work_item_use_cases import list_work_items as list_work_items_from_store
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency, clean_string_list


class WorkItemCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    status: WorkItemStatus = WorkItemStatus.QUEUED
    priority: WorkItemPriority = WorkItemPriority.MEDIUM
    goal_id: str | None = Field(default=None, max_length=48)
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    source: str = Field(default="manual", min_length=1, max_length=64)
    external_ref: str | None = Field(default=None, max_length=256)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    approval_required: bool = False
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description", "source", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "goal_id",
        "owner_agent_id",
        "owner_user_id",
        "external_ref",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("dependencies", mode="before")
    @classmethod
    def _clean_dependencies(cls, value: Any) -> list[str]:
        return clean_string_list(value)


class WorkItemStatusUpdateRequest(BaseModel):
    status: WorkItemStatus
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    actor_id: str = Field(default="api", min_length=1, max_length=128)


class WorkItemRunRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    agent_id: str | None = Field(default=None, max_length=64)
    input: dict[str, Any] = Field(default_factory=dict)
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, max_length=96)

    @field_validator("company_id", "agent_id", "trace_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("actor_id", mode="before")
    @classmethod
    def _clean_actor_id(cls, value: Any) -> str:
        return str(value or "api").strip() or "api"


class WorkItemRetryRequest(WorkItemRunRequest):
    pass


class WorkItemReassignRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=2_000)

    @field_validator("company_id", "owner_agent_id", "owner_user_id", "reason", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("actor_id", mode="before")
    @classmethod
    def _clean_actor_id(cls, value: Any) -> str:
        return str(value or "api").strip() or "api"


class WorkItemBlockRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    reason: str = Field(min_length=1, max_length=2_000)
    actor_id: str = Field(default="api", min_length=1, max_length=128)

    @field_validator("company_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("reason", "actor_id", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()


class WorkItemCloseRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    status: WorkItemStatus = WorkItemStatus.COMPLETED
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=2_000)

    @field_validator("company_id", "reason", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("actor_id", mode="before")
    @classmethod
    def _clean_actor_id(cls, value: Any) -> str:
        return str(value or "api").strip() or "api"


def create_work_item_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/work-items")
    async def list_work_items(
        company_id: str | None = None,
        status: WorkItemStatus | None = None,
        priority: WorkItemPriority | None = None,
        goal_id: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.work_items
        rows = await list_work_items_from_store(
            store,
            company_id=resolve_company(company_id),
            status=status.value if status else None,
            priority=priority.value if priority else None,
            goal_id=goal_id,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )
        return {"work_items": [row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/work-items",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_work_item(
        body: WorkItemCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.work_items
        company_id = resolve_company(body.company_id)
        try:
            row = await create_work_item_with_audit(
                store,
                WorkItem(
                    company_id=company_id,
                    title=body.title,
                    description=body.description,
                    status=body.status,
                    priority=body.priority,
                    goal_id=body.goal_id,
                    owner_agent_id=body.owner_agent_id,
                    owner_user_id=body.owner_user_id,
                    source=body.source,
                    external_ref=body.external_ref,
                    dependencies=body.dependencies,
                    approval_required=body.approval_required,
                    metadata=body.metadata,
                ),
                created_by=body.created_by,
            )
        except WorkItemGoalNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="goal_not_found")
        except WorkItemDependencyNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="dependency_not_found")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/work-items/{work_item_id}")
    async def get_work_item(
        work_item_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.work_items
        try:
            row = await get_work_item_from_store(
                store,
                company_id=resolve_company(company_id),
                work_item_id=work_item_id,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        return row_to_dict(row)

    @router.patch("/work-items/{work_item_id}/status")
    async def update_work_item_status(
        work_item_id: str,
        body: WorkItemStatusUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.work_items
        resolved_company_id = resolve_company(company_id)
        try:
            row = await update_work_item_status_with_audit(
                store,
                company_id=resolved_company_id,
                work_item_id=work_item_id,
                status=body.status,
                owner_agent_id=body.owner_agent_id,
                owner_user_id=body.owner_user_id,
                actor_id=body.actor_id,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        except InvalidWorkItemTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_work_item_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    @router.post("/work-items/{work_item_id}/run")
    async def run_work_item(
        work_item_id: str,
        body: WorkItemRunRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            result = await run_work_item_with_agent(
                stores.work_items,
                stores.agent_operations,
                company_id=resolve_company(body.company_id),
                work_item_id=work_item_id,
                agent_id=body.agent_id,
                input_payload=body.input,
                actor_id=body.actor_id,
                trace_id=body.trace_id,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        except WorkItemExecutionAgentRequiredError:
            raise_control_plane_api_error(status_code=400, detail="agent_required")
        except AgentDefinitionNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        except AgentWakeupError as exc:
            await uow.commit()
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.detail)
        except InvalidWorkItemTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_work_item_transition",
            )

        await uow.commit()
        return {
            "work_item": row_to_dict(result.work_item),
            "run": (
                row_to_dict(result.agent_wakeup.run)
                if result.agent_wakeup.run is not None
                else {"run_id": result.agent_wakeup.wakeup.run_id}
            ),
            "output": result.agent_wakeup.wakeup.output,
            "evidence_artifact_id": result.agent_wakeup.wakeup.evidence_artifact_id,
        }

    @router.post("/work-items/{work_item_id}/retry")
    async def retry_work_item(
        work_item_id: str,
        body: WorkItemRetryRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            result = await run_work_item_with_agent(
                stores.work_items,
                stores.agent_operations,
                company_id=resolve_company(body.company_id),
                work_item_id=work_item_id,
                agent_id=body.agent_id,
                input_payload=body.input,
                actor_id=body.actor_id,
                trace_id=body.trace_id,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        except WorkItemExecutionAgentRequiredError:
            raise_control_plane_api_error(status_code=400, detail="agent_required")
        except AgentDefinitionNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="agent_not_found")
        except AgentWakeupError as exc:
            await uow.commit()
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.detail)
        except InvalidWorkItemTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_work_item_transition",
            )

        await uow.commit()
        return {
            "work_item": row_to_dict(result.work_item),
            "run": (
                row_to_dict(result.agent_wakeup.run)
                if result.agent_wakeup.run is not None
                else {"run_id": result.agent_wakeup.wakeup.run_id}
            ),
            "output": result.agent_wakeup.wakeup.output,
            "evidence_artifact_id": result.agent_wakeup.wakeup.evidence_artifact_id,
        }

    @router.post("/work-items/{work_item_id}/reassign")
    async def reassign_work_item_route(
        work_item_id: str,
        body: WorkItemReassignRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            row = await reassign_work_item(
                stores.work_items,
                company_id=resolve_company(body.company_id),
                work_item_id=work_item_id,
                owner_agent_id=body.owner_agent_id,
                owner_user_id=body.owner_user_id,
                actor_id=body.actor_id,
                reason=body.reason,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        except WorkItemAssigneeRequiredError:
            raise_control_plane_api_error(status_code=400, detail="assignee_required")
        except InvalidWorkItemTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_work_item_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    @router.post("/work-items/{work_item_id}/block")
    async def block_work_item_route(
        work_item_id: str,
        body: WorkItemBlockRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            row = await block_work_item(
                stores.work_items,
                company_id=resolve_company(body.company_id),
                work_item_id=work_item_id,
                actor_id=body.actor_id,
                reason=body.reason,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        except InvalidWorkItemTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_work_item_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    @router.post("/work-items/{work_item_id}/close")
    async def close_work_item_route(
        work_item_id: str,
        body: WorkItemCloseRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            row = await close_work_item(
                stores.work_items,
                company_id=resolve_company(body.company_id),
                work_item_id=work_item_id,
                status=body.status,
                actor_id=body.actor_id,
                reason=body.reason,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        except WorkItemCloseStatusError:
            raise_control_plane_api_error(status_code=400, detail="invalid_close_status")
        except InvalidWorkItemTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_work_item_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    @router.get("/work-items/{work_item_id}/activity")
    async def get_work_item_activity(
        work_item_id: str,
        company_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        resolved_company_id = resolve_company(company_id)
        try:
            work_item = await get_work_item_from_store(
                stores.work_items,
                company_id=resolved_company_id,
                work_item_id=work_item_id,
            )
        except WorkItemNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="work_item_not_found")
        items = await build_work_item_activity_from_store(
            stores.audit_timeline,
            company_id=resolved_company_id,
            work_item_id=work_item_id,
            limit=limit,
        )
        return {
            "work_item": row_to_dict(work_item),
            "activity": [
                {
                    "type": item.item_type,
                    "at": serialize_value(item.at),
                    "data": row_to_dict(item.data),
                }
                for item in items
            ],
            "total": len(items),
        }

    return router
