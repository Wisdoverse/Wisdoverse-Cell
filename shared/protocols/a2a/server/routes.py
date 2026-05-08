"""
A2A FastAPI Routes

HTTP routes for A2A protocol endpoints.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from shared.schemas.agent import BaseAgent

from ..middleware.auth import (
    A2AAuthContext,
    check_rate_limit,
    get_optional_auth_context,
)
from .jsonrpc import A2AJSONRPCServer


def create_a2a_router(
    agent: BaseAgent,
    jsonrpc_server: A2AJSONRPCServer | None = None,
    prefix: str = "",
) -> APIRouter:
    """
    Create FastAPI router for A2A endpoints.

    Args:
        agent: The agent to expose via A2A.
        jsonrpc_server: Optional JSON-RPC server instance.
        prefix: URL prefix for routes.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix=prefix, tags=["A2A"])

    # Use provided server or create new one
    server = jsonrpc_server or A2AJSONRPCServer()

    # ============ Agent Card Discovery ============

    @router.get(
        "/.well-known/agent.json",
        response_model=None,
        summary="Get Agent Card",
        description="Returns the agent's public Agent Card for discovery.",
    )
    async def get_agent_card() -> dict[str, Any]:
        """Return the agent card for discovery."""
        if not agent.a2a_enabled:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="A2A protocol not enabled for this agent",
            )

        card = agent.get_agent_card()
        return card.to_well_known_json()

    @router.get(
        "/v1/card",
        response_model=None,
        summary="Get Agent Card (REST)",
        description="REST endpoint for Agent Card (alternative to .well-known).",
    )
    async def get_agent_card_rest() -> dict[str, Any]:
        """REST endpoint for agent card."""
        return await get_agent_card()

    # ============ JSON-RPC Endpoint ============

    @router.post(
        "/rpc",
        response_model=None,
        summary="JSON-RPC Endpoint",
        description="A2A JSON-RPC 2.0 endpoint for task operations.",
        dependencies=[Depends(check_rate_limit)],
    )
    async def jsonrpc_endpoint(
        request: Request,
        auth: A2AAuthContext | None = Depends(get_optional_auth_context),
    ) -> dict[str, Any]:
        """Handle JSON-RPC requests."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error",
                },
            }

        # Add auth context to request if available
        if auth and isinstance(body, dict):
            if "params" not in body:
                body["params"] = {}
            if isinstance(body["params"], dict):
                body["params"]["_auth"] = auth.model_dump()

        return await server.handle_request(body)

    # ============ Streaming Endpoint ============

    @router.post(
        "/rpc/stream",
        response_model=None,
        summary="Streaming JSON-RPC Endpoint",
        description="A2A JSON-RPC endpoint with SSE streaming response.",
        dependencies=[Depends(check_rate_limit)],
    )
    async def jsonrpc_stream_endpoint(
        request: Request,
        auth: A2AAuthContext | None = Depends(get_optional_auth_context),
    ) -> StreamingResponse:
        """Handle JSON-RPC requests with streaming response."""
        try:
            body = await request.json()
        except json.JSONDecodeError:

            async def error_gen() -> AsyncGenerator[str, None]:
                yield f"data: {json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}})}\n\n"

            return StreamingResponse(
                error_gen(),
                media_type="text/event-stream",
            )

        # Add auth context to request if available
        if auth and isinstance(body, dict):
            if "params" not in body:
                body["params"] = {}
            if isinstance(body["params"], dict):
                body["params"]["_auth"] = auth.model_dump()

        async def stream_gen() -> AsyncGenerator[str, None]:
            async for response in server.handle_request_streaming(body):
                yield f"data: {json.dumps(response)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ============ Task Status SSE ============

    @router.get(
        "/tasks/{task_id}/stream",
        response_model=None,
        summary="Task Status Stream",
        description="SSE stream for task status updates.",
        dependencies=[Depends(check_rate_limit)],
    )
    async def task_status_stream(
        task_id: str,
        auth: A2AAuthContext | None = Depends(get_optional_auth_context),
    ) -> StreamingResponse:
        """Stream task status updates via SSE."""
        task = await server._task_store.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task not found: {task_id}",
            )

        async def status_gen() -> AsyncGenerator[str, None]:
            last_status = None
            while True:
                current_task = await server._task_store.get_task(task_id)
                if current_task is None:
                    yield f"data: {json.dumps({'type': 'deleted'})}\n\n"
                    break

                if current_task.status != last_status:
                    last_status = current_task.status
                    yield f"data: {json.dumps({'type': 'status', 'task': current_task.model_dump(by_alias=True, exclude_none=True)})}\n\n"

                    if current_task.is_terminal():
                        break

                await asyncio.sleep(0.5)

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            status_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # ============ Health Check ============

    @router.get(
        "/health",
        summary="A2A Health Check",
        description="Check A2A endpoint health.",
    )
    async def health_check() -> dict[str, Any]:
        """Return A2A health status."""
        return {
            "status": "healthy",
            "agent_id": agent.agent_id,
            "a2a_enabled": agent.a2a_enabled,
            "protocol_version": "0.3.0",
        }

    return router


def mount_a2a_routes(
    app,
    agent: BaseAgent,
    jsonrpc_server: A2AJSONRPCServer | None = None,
) -> None:
    """
    Mount A2A routes on a FastAPI app.

    Args:
        app: FastAPI application instance.
        agent: The agent to expose via A2A.
        jsonrpc_server: Optional JSON-RPC server instance.
    """
    router = create_a2a_router(
        agent=agent,
        jsonrpc_server=jsonrpc_server,
        prefix="/a2a",
    )
    app.include_router(router)

    # Also mount the well-known endpoint at root
    @app.get("/.well-known/agent.json", include_in_schema=False)
    async def root_agent_card() -> dict[str, Any]:
        if not agent.a2a_enabled:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="A2A protocol not enabled for this agent",
            )
        return agent.get_agent_card().to_well_known_json()
