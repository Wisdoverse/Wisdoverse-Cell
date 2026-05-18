"""
gRPC servicer implementation.

Implements the RequirementService interface for the requirement manager agent.
"""
from typing import Optional

import grpc

from agents.requirement_manager.core.grpc_ports import RequirementGrpcStore
from agents.requirement_manager.core.health_ports import RequirementHealthStore
from agents.requirement_manager.db.database import db_manager
from agents.requirement_manager.db.grpc_store import SqlAlchemyRequirementGrpcStore
from agents.requirement_manager.db.health_store import SqlAlchemyRequirementHealthStore
from agents.requirement_manager.grpc import requirement_pb2 as pb2
from agents.requirement_manager.grpc import requirement_pb2_grpc as pb2_grpc
from agents.requirement_manager.models.requirement import Requirement, RequirementStatus
from agents.requirement_manager.service.agent import RequirementManagerAgent
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("grpc.servicer")


def _requirement_to_proto(req: Requirement) -> pb2.Requirement:
    """Convert SQLAlchemy Requirement to protobuf Requirement."""
    return pb2.Requirement(
        id=req.id,
        title=req.title,
        description=req.description or "",
        status=req.status,
        priority=req.priority,
        category=req.category,
        source_quote=req.source_quote or "",
        confirmed_by=req.confirmed_by or "",
        confirmed_at=int(req.confirmed_at.timestamp()) if req.confirmed_at else 0,
        rejection_reason=req.rejection_reason or "",
        created_at=int(req.created_at.timestamp()) if req.created_at else 0,
        updated_at=int(req.updated_at.timestamp()) if req.updated_at else 0,
    )


class RequirementServicer(pb2_grpc.RequirementServiceServicer):
    """
    gRPC Servicer for Requirement Management.

    Handles requests from the Rust gateway and delegates to the requirement manager agent.
    """

    def __init__(
        self,
        agent: Optional[RequirementManagerAgent] = None,
        requirement_store: RequirementGrpcStore | None = None,
        health_store: RequirementHealthStore | None = None,
    ):
        """
        Initialize the servicer.

        Args:
            agent: Optional RequirementManagerAgent instance. If not provided,
                   the servicer will work in stateless mode using only the repository.
        """
        self.agent = agent
        self._requirements = requirement_store or SqlAlchemyRequirementGrpcStore(
            db_manager
        )
        self._health_store = health_store or SqlAlchemyRequirementHealthStore(
            db_manager
        )
        logger.info("grpc_servicer_initialized", has_agent=agent is not None)

    async def ExtractRequirements(self, request: pb2.ExtractRequest, context) -> pb2.ExtractResponse:
        """
        Extract requirements from meeting content using LLM.
        """
        logger.info(
            "grpc_extract_requirements",
            content_length=len(request.content),
            source=request.source,
        )

        try:
            if not self.agent:
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details("Agent not initialized")
                return pb2.ExtractResponse(success=False, error="Agent not initialized")

            # Call agent's ingest_meeting method
            result = await self.agent.ingest_meeting(
                content=request.content,
                source=request.source or "grpc",
                context=request.context,
                participants=list(request.participants) if request.participants else None,
            )

            if result is None:
                return pb2.ExtractResponse(
                    success=False,
                    error="Failed to extract requirements",
                )

            # Convert requirements to protobuf
            proto_requirements = [
                _requirement_to_proto(req)
                for req in await self._requirements.get_many(
                    list(result.requirements)
                )
            ]

            return pb2.ExtractResponse(
                success=True,
                meeting_id=result.meeting_id,
                requirements=proto_requirements,
                questions_count=len(result.open_questions),
            )

        except Exception as e:
            logger.error("grpc_extract_requirements_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.ExtractResponse(success=False, error=str(e))

    async def ListRequirements(self, request: pb2.ListRequest, context) -> pb2.ListResponse:
        """
        List requirements with optional status filter.
        """
        logger.info(
            "grpc_list_requirements",
            status=request.status,
            page=request.page,
            page_size=request.page_size,
        )

        try:
            status_filter = None
            if request.status:
                status_upper = request.status.upper()
                if status_upper in [s.name for s in RequirementStatus]:
                    status_filter = RequirementStatus[status_upper].value

            page = request.page if request.page > 0 else 1
            page_size = request.page_size if request.page_size > 0 else 20
            requirements, total = await self._requirements.list_requirements(
                status=status_filter,
                page=page,
                page_size=page_size,
            )
            total_pages = (total + page_size - 1) // page_size

            return pb2.ListResponse(
                requirements=[_requirement_to_proto(r) for r in requirements],
                total=total,
                total_pages=total_pages,
            )

        except Exception as e:
            logger.error("grpc_list_requirements_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.ListResponse()

    async def GetRequirement(self, request: pb2.GetRequest, context) -> pb2.Requirement:
        """
        Get a single requirement by ID.
        """
        logger.info("grpc_get_requirement", id=request.id)

        try:
            req = await self._requirements.get_by_id(request.id)

            if not req:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Requirement {request.id} not found")
                return pb2.Requirement()

            return _requirement_to_proto(req)

        except Exception as e:
            logger.error("grpc_get_requirement_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.Requirement()

    async def ConfirmRequirement(self, request: pb2.ConfirmRequest, context) -> pb2.OperationResponse:
        """
        Confirm a pending requirement.
        """
        logger.info(
            "grpc_confirm_requirement",
            id=request.id,
            confirmed_by=request.confirmed_by,
        )

        try:
            if self.agent:
                # Use agent method for full workflow (events, etc.)
                result = await self.agent.confirm_requirement(
                    requirement_id=request.id,
                    confirmed_by=request.confirmed_by or "grpc_user",
                )

                if result:
                    return pb2.OperationResponse(
                        success=True,
                        requirement=_requirement_to_proto(result),
                    )
                else:
                    return pb2.OperationResponse(
                        success=False,
                        error="Failed to confirm requirement",
                    )
            else:
                req = await self._requirements.confirm(
                    request.id,
                    confirmed_by=request.confirmed_by or "grpc_user",
                )

                if req:
                    return pb2.OperationResponse(
                        success=True,
                        requirement=_requirement_to_proto(req),
                    )
                return pb2.OperationResponse(
                    success=False,
                    error="Requirement not found or already processed",
                )

        except Exception as e:
            logger.error("grpc_confirm_requirement_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.OperationResponse(success=False, error=str(e))

    async def RejectRequirement(self, request: pb2.RejectRequest, context) -> pb2.OperationResponse:
        """
        Reject a pending requirement.
        """
        logger.info(
            "grpc_reject_requirement",
            id=request.id,
            rejected_by_hash=hash_identifier(request.rejected_by),
            reason_length=len(request.reason or ""),
        )

        try:
            if self.agent:
                # Use agent method for full workflow
                result = await self.agent.reject_requirement(
                    requirement_id=request.id,
                    reason=request.reason or "Rejected via gateway",
                    rejected_by=request.rejected_by or "grpc_user",
                )

                if result:
                    return pb2.OperationResponse(
                        success=True,
                        requirement=_requirement_to_proto(result),
                    )
                else:
                    return pb2.OperationResponse(
                        success=False,
                        error="Failed to reject requirement",
                    )
            else:
                req = await self._requirements.reject(
                    request.id,
                    reason=request.reason or "Rejected via gateway",
                    rejected_by=request.rejected_by or "grpc_user",
                )

                if req:
                    return pb2.OperationResponse(
                        success=True,
                        requirement=_requirement_to_proto(req),
                    )
                return pb2.OperationResponse(
                    success=False,
                    error="Requirement not found or already processed",
                )

        except Exception as e:
            logger.error("grpc_reject_requirement_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.OperationResponse(success=False, error=str(e))

    async def SearchRequirements(self, request: pb2.SearchRequest, context) -> pb2.SearchResponse:
        """
        Search requirements by keyword.
        """
        logger.info(
            "grpc_search_requirements",
            keyword_length=len(request.keyword or ""),
            keyword_hash=hash_identifier(request.keyword),
            chat_hash=hash_identifier(request.chat_id),
        )

        try:
            page = request.page if request.page > 0 else 1
            page_size = request.page_size if request.page_size > 0 else 20
            requirements, total = await self._requirements.search_requirements(
                keyword=request.keyword,
                page=page,
                page_size=page_size,
            )

            return pb2.SearchResponse(
                requirements=[_requirement_to_proto(r) for r in requirements],
                total=total,
            )

        except Exception as e:
            logger.error("grpc_search_requirements_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SearchResponse()

    async def HealthCheck(self, request: pb2.HealthRequest, context) -> pb2.HealthResponse:
        """
        Check health of the requirement manager agent.
        """
        services = {}
        healthy = True

        db_ready = await self._health_store.is_database_ready()
        services["db"] = db_ready
        if not db_ready:
            healthy = False

        # Check agent if available
        if self.agent:
            services["agent"] = True
        else:
            services["agent"] = False

        return pb2.HealthResponse(
            healthy=healthy,
            version="1.0.0",
            services=services,
        )
