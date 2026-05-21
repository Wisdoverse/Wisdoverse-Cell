"""Artifact HTTP routes for the Control Plane API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..artifact_use_cases import (
    ArtifactGoalNotFoundError,
    ArtifactLinkMismatchError,
    ArtifactNotFoundError,
    ArtifactRunNotFoundError,
    ArtifactWorkItemNotFoundError,
    create_artifact_with_audit,
)
from ..artifact_use_cases import get_artifact as get_artifact_from_store
from ..artifact_use_cases import list_artifacts as list_artifacts_from_store
from ..models import Artifact, ArtifactType
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency


class ArtifactCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    artifact_type: ArtifactType = ArtifactType.OTHER
    title: str = Field(min_length=1, max_length=256)
    uri: str = Field(min_length=1, max_length=4_000)
    content_hash: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=48)
    work_item_id: str | None = Field(default=None, max_length=48)
    goal_id: str | None = Field(default=None, max_length=48)
    created_by_agent_id: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "uri", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "content_hash",
        "run_id",
        "work_item_id",
        "goal_id",
        "created_by_agent_id",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


def create_artifact_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/artifacts")
    async def list_artifacts(
        company_id: str | None = None,
        artifact_type: ArtifactType | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.artifacts
        rows = await list_artifacts_from_store(
            store,
            company_id=resolve_company(company_id),
            artifact_type=artifact_type.value if artifact_type else None,
            run_id=run_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            created_by_agent_id=created_by_agent_id,
            limit=limit,
        )
        return {"artifacts": [row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/artifacts",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_artifact(
        body: ArtifactCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.artifacts
        company_id = resolve_company(body.company_id)
        try:
            row = await create_artifact_with_audit(
                store,
                Artifact(
                    company_id=company_id,
                    artifact_type=body.artifact_type,
                    title=body.title,
                    uri=body.uri,
                    content_hash=body.content_hash,
                    run_id=body.run_id,
                    work_item_id=body.work_item_id,
                    goal_id=body.goal_id,
                    created_by_agent_id=body.created_by_agent_id,
                    metadata=body.metadata,
                ),
                created_by=body.created_by,
            )
        except ArtifactRunNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="run_not_found")
        except ArtifactWorkItemNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="work_item_not_found")
        except ArtifactGoalNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="goal_not_found")
        except ArtifactLinkMismatchError:
            raise_control_plane_api_error(status_code=400, detail="link_mismatch")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.artifacts
        try:
            row = await get_artifact_from_store(
                store,
                company_id=resolve_company(company_id),
                artifact_id=artifact_id,
            )
        except ArtifactNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="artifact_not_found")
        return row_to_dict(row)

    return router
