"""
gRPC Server

Provides the gRPC server for Go Gateway communication.
"""
import asyncio
import os
from concurrent import futures
from typing import Optional

from grpc import aio

from agents.requirement_manager.grpc import requirement_pb2 as pb2
from agents.requirement_manager.grpc import requirement_pb2_grpc as pb2_grpc
from agents.requirement_manager.grpc.servicer import RequirementServicer
from agents.requirement_manager.service.agent import RequirementManagerAgent
from shared.utils.logger import get_logger

logger = get_logger("grpc.server")

# Default gRPC port
DEFAULT_GRPC_PORT = 50051


async def create_server(
    agent: Optional[RequirementManagerAgent] = None,
    port: int = None,
) -> aio.Server:
    """
    Create a gRPC server instance.

    Args:
        agent: Optional RequirementManagerAgent for full functionality.
        port: Port to listen on. Defaults to GRPC_PORT env var or 50051.

    Returns:
        Configured gRPC server (not yet started).
    """
    if port is None:
        port = int(os.environ.get("GRPC_PORT", DEFAULT_GRPC_PORT))

    server = aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.keepalive_time_ms", 30000),  # 30s
            ("grpc.keepalive_timeout_ms", 10000),  # 10s
            ("grpc.keepalive_permit_without_calls", True),
        ],
    )

    # Add servicer
    servicer = RequirementServicer(agent=agent)
    pb2_grpc.add_RequirementServiceServicer_to_server(servicer, server)

    # Add reflection for debugging (optional)
    try:
        from grpc_reflection.v1alpha import reflection
        SERVICE_NAMES = (
            pb2.DESCRIPTOR.services_by_name["RequirementService"].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        logger.info("grpc_reflection_enabled")
    except (ImportError, AttributeError):
        logger.debug("grpc_reflection_not_available")

    # Listen on port
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info("grpc_server_created", port=port)
    return server


async def serve(
    agent: Optional[RequirementManagerAgent] = None,
    port: int = None,
) -> None:
    """
    Start and run the gRPC server.

    Args:
        agent: Optional RequirementManagerAgent for full functionality.
        port: Port to listen on.
    """
    if port is None:
        port = int(os.environ.get("GRPC_PORT", DEFAULT_GRPC_PORT))

    server = await create_server(agent=agent, port=port)
    await server.start()

    logger.info("grpc_server_started", port=port)
    print(f"gRPC server listening on port {port}")

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("grpc_server_shutting_down")
        await server.stop(grace=5)
        logger.info("grpc_server_stopped")


async def run_with_fastapi(
    agent: Optional[RequirementManagerAgent] = None,
    grpc_port: int = None,
) -> aio.Server:
    """
    Start gRPC server to run alongside FastAPI.

    This function starts the gRPC server in the background and returns
    the server instance for lifecycle management.

    Args:
        agent: Optional RequirementManagerAgent for full functionality.
        grpc_port: Port for gRPC server.

    Returns:
        Started gRPC server instance.
    """
    if grpc_port is None:
        grpc_port = int(os.environ.get("GRPC_PORT", DEFAULT_GRPC_PORT))

    server = await create_server(agent=agent, port=grpc_port)
    await server.start()

    logger.info("grpc_server_started_with_fastapi", port=grpc_port)
    return server


if __name__ == "__main__":
    # Standalone gRPC server for testing
    asyncio.run(serve())
