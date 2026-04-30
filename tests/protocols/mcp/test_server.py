"""Tests for MCP Server."""

import pytest

from shared.protocols.mcp.server.base import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PROMPT_NOT_FOUND,
    RESOURCE_NOT_FOUND,
    TOOL_NOT_FOUND,
    MCPServer,
)
from shared.protocols.mcp.server.router import MCPRouter


class TestMCPServer:
    """Tests for MCPServer."""

    @pytest.fixture
    def router(self) -> MCPRouter:
        """Create a router with some tools/resources/prompts."""
        router = MCPRouter()

        @router.tool()
        def calculate(a: int, b: int, operation: str = "add") -> int:
            """Perform a calculation."""
            if operation == "add":
                return a + b
            elif operation == "multiply":
                return a * b
            return 0

        @router.resource("config://app")
        def get_config() -> dict:
            """Get application config."""
            return {"debug": True, "version": "1.0"}

        @router.resource("user://{user_id}")
        def get_user(user_id: str) -> dict:
            """Get user by ID."""
            return {"id": user_id, "name": f"User {user_id}"}

        @router.prompt()
        def summarize(text: str, style: str = "concise") -> str:
            """Summarize text prompt."""
            return f"Please summarize the following text in a {style} style:\n\n{text}"

        return router

    @pytest.fixture
    def server(self, router: MCPRouter) -> MCPServer:
        """Create a server with the router."""
        return MCPServer(name="Test Server", version="1.0.0", router=router)

    @pytest.mark.asyncio
    async def test_initialize(self, server: MCPServer):
        """Test initialize method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
        })

        assert "result" in response
        assert response["result"]["serverInfo"]["name"] == "Test Server"
        assert "capabilities" in response["result"]

    @pytest.mark.asyncio
    async def test_invalid_request(self, server: MCPServer):
        """Test handling invalid request."""
        response = await server.handle_request({
            "invalid": "request",
        })

        assert "error" in response
        assert response["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_method_not_found(self, server: MCPServer):
        """Test handling unknown method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "unknown/method",
        })

        assert "error" in response
        assert response["error"]["code"] == METHOD_NOT_FOUND

    # ============ Tools Tests ============

    @pytest.mark.asyncio
    async def test_tools_list(self, server: MCPServer):
        """Test tools/list method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/list",
        })

        assert "result" in response
        assert "tools" in response["result"]
        assert len(response["result"]["tools"]) == 1
        assert response["result"]["tools"][0]["name"] == "calculate"

    @pytest.mark.asyncio
    async def test_tools_call(self, server: MCPServer):
        """Test tools/call method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {
                "name": "calculate",
                "arguments": {"a": 5, "b": 3, "operation": "add"},
            },
        })

        assert "result" in response
        assert response["result"]["isError"] is False
        assert "content" in response["result"]
        # Result should be 8 serialized as text
        assert "8" in response["result"]["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_tools_call_multiply(self, server: MCPServer):
        """Test tools/call with multiply operation."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {
                "name": "calculate",
                "arguments": {"a": 4, "b": 7, "operation": "multiply"},
            },
        })

        assert "result" in response
        assert "28" in response["result"]["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_tools_call_missing_name(self, server: MCPServer):
        """Test tools/call without name."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {
                "arguments": {"a": 1, "b": 2},
            },
        })

        assert "error" in response
        assert response["error"]["code"] == INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_tools_call_not_found(self, server: MCPServer):
        """Test tools/call with nonexistent tool."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {
                "name": "nonexistent",
                "arguments": {},
            },
        })

        assert "error" in response
        assert response["error"]["code"] == TOOL_NOT_FOUND

    # ============ Resources Tests ============

    @pytest.mark.asyncio
    async def test_resources_list(self, server: MCPServer):
        """Test resources/list method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "resources/list",
        })

        assert "result" in response
        assert "resources" in response["result"]
        assert len(response["result"]["resources"]) == 2

    @pytest.mark.asyncio
    async def test_resources_read(self, server: MCPServer):
        """Test resources/read method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "resources/read",
            "params": {"uri": "config://app"},
        })

        assert "result" in response
        assert "contents" in response["result"]
        content = response["result"]["contents"][0]
        assert content["uri"] == "config://app"
        assert "debug" in content["text"]

    @pytest.mark.asyncio
    async def test_resources_read_with_params(self, server: MCPServer):
        """Test resources/read with URI parameters."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "resources/read",
            "params": {"uri": "user://42"},
        })

        assert "result" in response
        content = response["result"]["contents"][0]
        assert '"id": "42"' in content["text"]

    @pytest.mark.asyncio
    async def test_resources_read_missing_uri(self, server: MCPServer):
        """Test resources/read without URI."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "resources/read",
            "params": {},
        })

        assert "error" in response
        assert response["error"]["code"] == INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_resources_read_not_found(self, server: MCPServer):
        """Test resources/read with nonexistent resource."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "resources/read",
            "params": {"uri": "nonexistent://resource"},
        })

        assert "error" in response
        assert response["error"]["code"] == RESOURCE_NOT_FOUND

    # ============ Prompts Tests ============

    @pytest.mark.asyncio
    async def test_prompts_list(self, server: MCPServer):
        """Test prompts/list method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "prompts/list",
        })

        assert "result" in response
        assert "prompts" in response["result"]
        assert len(response["result"]["prompts"]) == 1
        assert response["result"]["prompts"][0]["name"] == "summarize"

    @pytest.mark.asyncio
    async def test_prompts_get(self, server: MCPServer):
        """Test prompts/get method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "prompts/get",
            "params": {
                "name": "summarize",
                "arguments": {"text": "This is a long text.", "style": "brief"},
            },
        })

        assert "result" in response
        assert "messages" in response["result"]
        message = response["result"]["messages"][0]
        assert message["role"] == "user"
        assert "brief" in message["content"]["text"]
        assert "long text" in message["content"]["text"]

    @pytest.mark.asyncio
    async def test_prompts_get_missing_name(self, server: MCPServer):
        """Test prompts/get without name."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "prompts/get",
            "params": {},
        })

        assert "error" in response
        assert response["error"]["code"] == INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_prompts_get_not_found(self, server: MCPServer):
        """Test prompts/get with nonexistent prompt."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "prompts/get",
            "params": {"name": "nonexistent"},
        })

        assert "error" in response
        assert response["error"]["code"] == PROMPT_NOT_FOUND

    # ============ Server Properties ============

    def test_server_name(self, server: MCPServer):
        """Test server name property."""
        assert server.name == "Test Server"

    def test_server_version(self, server: MCPServer):
        """Test server version property."""
        assert server.version == "1.0.0"

    def test_set_router(self):
        """Test setting router after construction."""
        server = MCPServer(name="Empty Server", version="1.0.0")
        router = MCPRouter()

        @router.tool()
        def test_tool() -> str:
            return "test"

        server.set_router(router)

        assert len(server.router.get_tools()) == 1
