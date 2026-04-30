"""
MCP Server

Base MCP server implementation for handling tool/resource/prompt requests.
"""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .router import MCPRouter


class MCPRequest(BaseModel):
    """MCP JSON-RPC request."""

    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    id: str | int | None = Field(default=None, description="Request ID")
    method: str = Field(..., description="Method name")
    params: dict[str, Any] | None = Field(default=None, description="Method parameters")


class MCPError(BaseModel):
    """MCP error response."""

    model_config = ConfigDict(extra="forbid")

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Any | None = Field(default=None, description="Additional error data")


class MCPResponse(BaseModel):
    """MCP JSON-RPC response."""

    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    id: str | int | None = Field(default=None, description="Request ID")
    result: Any | None = Field(default=None, description="Result (on success)")
    error: MCPError | None = Field(default=None, description="Error (on failure)")


# MCP Error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# MCP specific errors
TOOL_NOT_FOUND = -32001
RESOURCE_NOT_FOUND = -32002
PROMPT_NOT_FOUND = -32003


class MCPServer:
    """
    MCP Server for handling tool, resource, and prompt requests.

    Supports:
    - tools/list: List available tools
    - tools/call: Call a tool
    - resources/list: List available resources
    - resources/read: Read a resource
    - prompts/list: List available prompts
    - prompts/get: Get a prompt
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        router: MCPRouter | None = None,
    ):
        """
        Initialize MCP Server.

        Args:
            name: Server name.
            version: Server version.
            router: Optional MCPRouter with registered tools/resources/prompts.
        """
        self._name = name
        self._version = version
        self._router = router or MCPRouter()

    @property
    def name(self) -> str:
        """Get server name."""
        return self._name

    @property
    def version(self) -> str:
        """Get server version."""
        return self._version

    @property
    def router(self) -> MCPRouter:
        """Get the MCP router."""
        return self._router

    def set_router(self, router: MCPRouter) -> None:
        """Set the MCP router."""
        self._router = router

    async def handle_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle an MCP request.

        Args:
            request_data: The parsed JSON-RPC request.

        Returns:
            JSON-RPC response dictionary.
        """
        try:
            request = MCPRequest.model_validate(request_data)
        except Exception as e:
            return MCPResponse(
                id=request_data.get("id"),
                error=MCPError(
                    code=INVALID_REQUEST,
                    message=f"Invalid request: {e}",
                ),
            ).model_dump(exclude_none=True)

        # Dispatch to method handler
        method_handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
        }

        handler = method_handlers.get(request.method)
        if handler is None:
            return MCPResponse(
                id=request.id,
                error=MCPError(
                    code=METHOD_NOT_FOUND,
                    message=f"Method not found: {request.method}",
                ),
            ).model_dump(exclude_none=True)

        try:
            result = await handler(request.params or {})
            return MCPResponse(
                id=request.id,
                result=result,
            ).model_dump(exclude_none=True)
        except MCPException as e:
            return MCPResponse(
                id=request.id,
                error=MCPError(
                    code=e.code,
                    message=e.message,
                    data=e.data,
                ),
            ).model_dump(exclude_none=True)
        except Exception as e:
            return MCPResponse(
                id=request.id,
                error=MCPError(
                    code=INTERNAL_ERROR,
                    message=f"Internal error: {e}",
                ),
            ).model_dump(exclude_none=True)

    async def _handle_initialize(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle initialize method."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": False, "listChanged": True},
                "prompts": {"listChanged": True},
            },
            "serverInfo": {
                "name": self._name,
                "version": self._version,
            },
        }

    async def _handle_tools_list(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle tools/list method."""
        tools = self._router.get_tools()
        return {"tools": tools}

    async def _handle_tools_call(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle tools/call method."""
        name = params.get("name")
        if not name:
            raise MCPException(INVALID_PARAMS, "Tool name is required")

        arguments = params.get("arguments", {})

        try:
            result = await self._router.call_tool(name, arguments)
        except ValueError as e:
            raise MCPException(TOOL_NOT_FOUND, str(e))

        # Format result as MCP content
        if isinstance(result, dict):
            content = [{"type": "text", "text": json.dumps(result, default=str)}]
        elif isinstance(result, str):
            content = [{"type": "text", "text": result}]
        elif isinstance(result, list):
            content = [{"type": "text", "text": json.dumps(result, default=str)}]
        else:
            content = [{"type": "text", "text": str(result)}]

        return {"content": content, "isError": False}

    async def _handle_resources_list(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle resources/list method."""
        resources = self._router.get_resources()
        return {"resources": resources}

    async def _handle_resources_read(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle resources/read method."""
        uri = params.get("uri")
        if not uri:
            raise MCPException(INVALID_PARAMS, "Resource URI is required")

        try:
            content, mime_type = await self._router.read_resource(uri)
        except ValueError as e:
            raise MCPException(RESOURCE_NOT_FOUND, str(e))

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

    async def _handle_prompts_list(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle prompts/list method."""
        prompts = self._router.get_prompts()
        return {"prompts": prompts}

    async def _handle_prompts_get(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle prompts/get method."""
        name = params.get("name")
        if not name:
            raise MCPException(INVALID_PARAMS, "Prompt name is required")

        arguments = params.get("arguments", {})

        try:
            content = await self._router.get_prompt_content(name, arguments)
        except ValueError as e:
            raise MCPException(PROMPT_NOT_FOUND, str(e))

        return {
            "description": f"Prompt: {name}",
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": content},
                }
            ],
        }


class MCPException(Exception):
    """Exception for MCP errors."""

    def __init__(
        self,
        code: int,
        message: str,
        data: Any | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
