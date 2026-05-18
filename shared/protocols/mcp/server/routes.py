"""
MCP FastAPI Routes

HTTP routes for MCP protocol endpoints.
"""

import json
from typing import Any

from fastapi import APIRouter, Request

from shared.api import (
    raise_mcp_invalid_json,
    raise_mcp_prompt_not_found,
    raise_mcp_resource_not_found,
    raise_mcp_tool_execution_failed,
    raise_mcp_tool_name_required,
    raise_mcp_tool_not_found,
)
from shared.utils.logger import get_logger

from .base import MCPServer

logger = get_logger("mcp.routes")


def create_mcp_router(
    mcp_server: MCPServer,
    prefix: str = "",
) -> APIRouter:
    """
    Create FastAPI router for MCP endpoints.

    Args:
        mcp_server: The MCP server instance.
        prefix: URL prefix for routes.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix=prefix, tags=["MCP"])

    # ============ JSON-RPC Endpoint ============

    @router.post(
        "/rpc",
        response_model=None,
        summary="MCP JSON-RPC Endpoint",
        description="Handle MCP JSON-RPC requests.",
    )
    async def jsonrpc_endpoint(request: Request) -> dict[str, Any]:
        """Handle MCP JSON-RPC requests."""
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

        return await mcp_server.handle_request(body)

    # ============ REST-style Endpoints ============

    @router.get(
        "/tools",
        summary="List MCP Tools",
        description="List all available MCP tools.",
    )
    async def list_tools() -> dict[str, Any]:
        """List all available tools."""
        tools = mcp_server.router.get_tools()
        return {"tools": tools}

    @router.post(
        "/tools/call",
        summary="Call MCP Tool",
        description="Call an MCP tool by name.",
    )
    async def call_tool(request: Request) -> dict[str, Any]:
        """Call a tool."""
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            logger.warning("mcp_tool_call_invalid_json", error=str(exc))
            raise_mcp_invalid_json()

        name = body.get("name")
        if not name:
            raise_mcp_tool_name_required()

        arguments = body.get("arguments", {})

        try:
            result = await mcp_server.router.call_tool(name, arguments)
        except ValueError as exc:
            logger.warning("mcp_tool_not_found", tool=name, error=str(exc))
            raise_mcp_tool_not_found()
        except Exception as exc:
            logger.error("mcp_tool_execution_failed", tool=name, error=str(exc))
            raise_mcp_tool_execution_failed()

        # Format result
        if isinstance(result, dict):
            content = [{"type": "text", "text": json.dumps(result, default=str)}]
        elif isinstance(result, str):
            content = [{"type": "text", "text": result}]
        else:
            content = [{"type": "text", "text": str(result)}]

        return {"content": content, "isError": False}

    @router.get(
        "/tools/{tool_name}",
        summary="Get Tool Schema",
        description="Get the schema for a specific tool.",
    )
    async def get_tool_schema(tool_name: str) -> dict[str, Any]:
        """Get tool schema."""
        tool = mcp_server.router.get_tool(tool_name)
        if tool is None:
            raise_mcp_tool_not_found()

        return {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }

    # ============ Resources ============

    @router.get(
        "/resources",
        summary="List MCP Resources",
        description="List all available MCP resources.",
    )
    async def list_resources() -> dict[str, Any]:
        """List all available resources."""
        resources = mcp_server.router.get_resources()
        return {"resources": resources}

    @router.get(
        "/resources/read",
        summary="Read MCP Resource",
        description="Read a resource by URI.",
    )
    async def read_resource(uri: str) -> dict[str, Any]:
        """Read a resource."""
        try:
            content, mime_type = await mcp_server.router.read_resource(uri)
        except ValueError as exc:
            logger.warning("mcp_resource_not_found", uri=uri, error=str(exc))
            raise_mcp_resource_not_found()

        # Format content
        if isinstance(content, dict):
            text = json.dumps(content, default=str)
        elif isinstance(content, str):
            text = content
        else:
            text = str(content)

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": mime_type,
                    "text": text,
                }
            ]
        }

    # ============ Prompts ============

    @router.get(
        "/prompts",
        summary="List MCP Prompts",
        description="List all available MCP prompts.",
    )
    async def list_prompts() -> dict[str, Any]:
        """List all available prompts."""
        prompts = mcp_server.router.get_prompts()
        return {"prompts": prompts}

    @router.post(
        "/prompts/{prompt_name}",
        summary="Get MCP Prompt",
        description="Get a prompt by name with arguments.",
    )
    async def get_prompt(prompt_name: str, request: Request) -> dict[str, Any]:
        """Get a prompt."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}

        arguments = body.get("arguments", {})

        try:
            content = await mcp_server.router.get_prompt_content(prompt_name, arguments)
        except ValueError as exc:
            logger.warning("mcp_prompt_not_found", prompt=prompt_name, error=str(exc))
            raise_mcp_prompt_not_found()

        return {
            "description": f"Prompt: {prompt_name}",
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": content},
                }
            ],
        }

    @router.get(
        "/prompts/{prompt_name}",
        summary="Get MCP Prompt Schema",
        description="Get the schema for a specific prompt.",
    )
    async def get_prompt_schema(prompt_name: str) -> dict[str, Any]:
        """Get prompt schema."""
        prompt = mcp_server.router.get_prompt(prompt_name)
        if prompt is None:
            raise_mcp_prompt_not_found()

        return {
            "name": prompt.name,
            "description": prompt.description,
            "arguments": prompt.arguments,
        }

    # ============ Health ============

    @router.get(
        "/health",
        summary="MCP Health Check",
        description="Check MCP server health.",
    )
    async def health_check() -> dict[str, Any]:
        """Return MCP health status."""
        return {
            "status": "healthy",
            "server": mcp_server.name,
            "version": mcp_server.version,
            "tools_count": len(mcp_server.router.get_tools()),
            "resources_count": len(mcp_server.router.get_resources()),
            "prompts_count": len(mcp_server.router.get_prompts()),
        }

    return router


def mount_mcp_routes(
    app,
    mcp_server: MCPServer,
) -> None:
    """
    Mount MCP routes on a FastAPI app.

    Args:
        app: FastAPI application instance.
        mcp_server: The MCP server instance.
    """
    router = create_mcp_router(
        mcp_server=mcp_server,
        prefix="/mcp",
    )
    app.include_router(router)
