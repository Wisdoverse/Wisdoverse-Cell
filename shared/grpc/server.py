"""
gRPC Server for Python AI Core.

This server exposes the RequirementService for the Go Gateway to consume.
"""
import asyncio
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

from shared.utils.logger import get_logger

# Import generated protobuf code
# Run `make proto` in project root to generate these
try:
    from shared.grpc.generated import requirement_pb2, requirement_pb2_grpc
except ImportError:
    requirement_pb2 = None
    requirement_pb2_grpc = None

logger = get_logger("grpc.server")


class RequirementServicer:
    """
    gRPC service implementation for RequirementService.

    Wraps the existing RequirementManagerAgent to expose via gRPC.
    """

    def __init__(self, agent):
        """
        Initialize with the RequirementManagerAgent.

        Args:
            agent: The RequirementManagerAgent instance.
        """
        self.agent = agent

    async def HealthCheck(self, request, context):
        """Health check endpoint."""
        return requirement_pb2.HealthResponse(
            healthy=True,
            version="1.0.0",
            services={
                "db": True,
                "redis": True,
                "llm": True,
            },
        )

    async def ListRequirements(self, request, context):
        """List requirements with pagination."""
        try:
            # TODO: pass status filter to agent.list_pending_requirements
            _ = request.status or "PENDING"
            page = request.page or 1
            page_size = request.page_size or 20

            requirements, total, total_pages = await self.agent.list_pending_requirements(
                page=page,
                page_size=page_size,
            )

            pb_requirements = [
                self._to_pb_requirement(req) for req in requirements
            ]

            return requirement_pb2.ListResponse(
                requirements=pb_requirements,
                total=total,
                total_pages=total_pages,
            )
        except Exception as e:
            logger.error("ListRequirements failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return requirement_pb2.ListResponse()

    async def GetRequirement(self, request, context):
        """Get a single requirement by ID."""
        try:
            requirement = await self.agent.get_requirement(request.id)
            if not requirement:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Requirement {request.id} not found")
                return requirement_pb2.Requirement()

            return self._to_pb_requirement_from_model(requirement)
        except Exception as e:
            logger.error("GetRequirement failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return requirement_pb2.Requirement()

    async def ConfirmRequirement(self, request, context):
        """Confirm a requirement."""
        try:
            async with self.agent._db_manager.session() as session:
                requirement = await self.agent.confirm_requirement(
                    requirement_id=request.id,
                    confirmed_by=request.confirmed_by,
                    session=session,
                )
                await session.commit()

            if not requirement:
                return requirement_pb2.OperationResponse(
                    success=False,
                    error=f"Requirement {request.id} not found or already processed",
                )

            return requirement_pb2.OperationResponse(
                success=True,
                requirement=self._to_pb_requirement_from_model(requirement),
            )
        except Exception as e:
            logger.error("ConfirmRequirement failed", error=str(e))
            return requirement_pb2.OperationResponse(
                success=False,
                error=str(e),
            )

    async def RejectRequirement(self, request, context):
        """Reject a requirement."""
        try:
            async with self.agent._db_manager.session() as session:
                requirement = await self.agent.reject_requirement(
                    requirement_id=request.id,
                    reason=request.reason,
                    rejected_by=request.rejected_by,
                    session=session,
                )
                await session.commit()

            if not requirement:
                return requirement_pb2.OperationResponse(
                    success=False,
                    error=f"Requirement {request.id} not found or already processed",
                )

            return requirement_pb2.OperationResponse(
                success=True,
                requirement=self._to_pb_requirement_from_model(requirement),
            )
        except Exception as e:
            logger.error("RejectRequirement failed", error=str(e))
            return requirement_pb2.OperationResponse(
                success=False,
                error=str(e),
            )

    async def ExtractRequirements(self, request, context):
        """Extract requirements from content using LLM."""
        try:
            async with self.agent._db_manager.session() as session:
                result = await self.agent.ingest_meeting(
                    content=request.content,
                    source=request.source or "grpc",
                    session=session,
                    context=request.context,
                    participants=list(request.participants) if request.participants else None,
                )
                await session.commit()

            return requirement_pb2.ExtractResponse(
                success=True,
                meeting_id=result.meeting_id,
                requirements=[],  # Could populate if needed
                questions_count=result.questions_generated,
            )
        except Exception as e:
            logger.error("ExtractRequirements failed", error=str(e))
            return requirement_pb2.ExtractResponse(
                success=False,
                error=str(e),
            )

    async def SearchRequirements(self, request, context):
        """Search requirements by keyword."""
        # Placeholder - implement when needed
        return requirement_pb2.SearchResponse(
            requirements=[],
            total=0,
        )

    def _to_pb_requirement(self, req_dict: dict):
        """Convert dict to protobuf Requirement."""
        return requirement_pb2.Requirement(
            id=req_dict.get("id", ""),
            title=req_dict.get("title", ""),
            description=req_dict.get("description", ""),
            status=req_dict.get("status", ""),
            priority=req_dict.get("priority", ""),
            category=req_dict.get("category", ""),
        )

    def _to_pb_requirement_from_model(self, req):
        """Convert SQLAlchemy model to protobuf Requirement."""
        return requirement_pb2.Requirement(
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


async def serve(agent, port: int = 50051):
    """
    Start the gRPC server.

    Args:
        agent: RequirementManagerAgent instance.
        port: Port to listen on.
    """
    if requirement_pb2 is None:
        logger.error("gRPC proto files not generated. Run 'make proto' first.")
        return

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add service
    servicer = RequirementServicer(agent)
    requirement_pb2_grpc.add_RequirementServiceServicer_to_server(servicer, server)

    # Enable reflection for debugging
    SERVICE_NAMES = (
        requirement_pb2.DESCRIPTOR.services_by_name["RequirementService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    # Start server
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info("gRPC server starting", port=port)
    await server.start()

    logger.info("gRPC server started", addr=listen_addr)
    await server.wait_for_termination()


if __name__ == "__main__":
    # Standalone testing
    from agents.requirement_manager.service.agent import agent

    asyncio.run(serve(agent, 50051))
