"""Authenticated HTTP routes for company knowledge pointers."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..knowledge_use_cases import (
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeOwnerRequiredError,
    KnowledgeProvenanceImmutableError,
    KnowledgeReadForbiddenError,
    KnowledgeRoleNotFoundError,
    KnowledgeSourceArtifactError,
    delete_knowledge,
    publish_knowledge,
    read_knowledge,
)
from ..operator_auth import OperatorPrincipal, require_operator
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgePublishRequest(_Request):
    company_id: str = Field(min_length=1, max_length=48)
    source_artifact_id: str = Field(min_length=1, max_length=48)
    reader_role_ids: list[str] = Field(default_factory=list, max_length=100)
    retention_until: datetime | None = None


class KnowledgeReviseRequest(KnowledgePublishRequest):
    expected_version: int = Field(ge=1)


def create_knowledge_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.post("/knowledge", status_code=http_status.HTTP_201_CREATED)
    async def publish(
        body: KnowledgePublishRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        company_id = resolve_company(body.company_id)
        principal.require("knowledge:write", company_id)
        try:
            record = await publish_knowledge(
                uow.stores.knowledge,
                company_id=company_id,
                source_artifact_id=body.source_artifact_id,
                actor_id=principal.actor_id,
                reader_role_ids=tuple(body.reader_role_ids),
                retention_until=body.retention_until,
            )
        except KnowledgeSourceArtifactError:
            raise_control_plane_api_error(
                status_code=400, detail="knowledge_source_artifact_invalid"
            )
        except KnowledgeRoleNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="knowledge_reader_role_invalid")
        await uow.commit()
        return row_to_dict(record)

    @router.post("/knowledge/{knowledge_id}/publish")
    async def revise(
        knowledge_id: str,
        body: KnowledgeReviseRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        company_id = resolve_company(body.company_id)
        principal.require("knowledge:write", company_id)
        try:
            record = await publish_knowledge(
                uow.stores.knowledge,
                company_id=company_id,
                source_artifact_id=body.source_artifact_id,
                actor_id=principal.actor_id,
                reader_role_ids=tuple(body.reader_role_ids),
                retention_until=body.retention_until,
                knowledge_id=knowledge_id,
                expected_version=body.expected_version,
            )
        except KnowledgeSourceArtifactError:
            raise_control_plane_api_error(
                status_code=400, detail="knowledge_source_artifact_invalid"
            )
        except KnowledgeRoleNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="knowledge_reader_role_invalid")
        except KnowledgeProvenanceImmutableError:
            raise_control_plane_api_error(status_code=400, detail="knowledge_provenance_immutable")
        except KnowledgeConflictError:
            raise_control_plane_api_error(status_code=409, detail="knowledge_version_conflict")
        except KnowledgeOwnerRequiredError:
            raise_control_plane_api_error(status_code=403, detail="knowledge_owner_required")
        except KnowledgeNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="knowledge_not_found")
        await uow.commit()
        return row_to_dict(record)

    @router.get("/knowledge/{knowledge_id}")
    async def read(
        knowledge_id: str,
        company_id: str = Query(min_length=1, max_length=48),
        stores: ControlPlaneStores = Depends(get_stores),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        company_id = resolve_company(company_id)
        principal.require("knowledge:read", company_id)
        try:
            record = await read_knowledge(
                stores.knowledge,
                knowledge_id=knowledge_id,
                company_id=company_id,
                actor_id=principal.actor_id,
                actor_role_ids=principal.role_ids,
                actor_scopes=principal.scopes,
            )
        except KnowledgeReadForbiddenError:
            raise_control_plane_api_error(status_code=403, detail="knowledge_reader_role_required")
        except KnowledgeNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="knowledge_not_found")
        source_artifact = await stores.knowledge.get_artifact(record.source_artifact_id)
        if source_artifact is None or source_artifact.company_id != company_id:
            raise_control_plane_api_error(
                status_code=404, detail="knowledge_source_artifact_invalid"
            )
        return {
            "knowledge": row_to_dict(record),
            "source_artifact": {
                "artifact_id": source_artifact.artifact_id,
                "company_id": source_artifact.company_id,
                "uri": source_artifact.uri,
                "content_hash": source_artifact.content_hash,
            },
        }

    @router.delete("/knowledge/{knowledge_id}")
    async def delete(
        knowledge_id: str,
        company_id: str = Query(min_length=1, max_length=48),
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        company_id = resolve_company(company_id)
        principal.require("knowledge:delete", company_id)
        try:
            tombstone = await delete_knowledge(
                uow.stores.knowledge,
                knowledge_id=knowledge_id,
                company_id=company_id,
                actor_id=principal.actor_id,
            )
        except KnowledgeOwnerRequiredError:
            raise_control_plane_api_error(status_code=403, detail="knowledge_owner_required")
        except KnowledgeConflictError:
            raise_control_plane_api_error(status_code=409, detail="knowledge_version_conflict")
        except KnowledgeNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="knowledge_not_found")
        await uow.commit()
        return row_to_dict(tombstone)

    return router
