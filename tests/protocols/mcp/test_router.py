"""Tests for MCP Router."""

import pytest

from shared.protocols.mcp.server.router import MCPRouter


class TestMCPRouter:
    """Tests for MCPRouter."""

    @pytest.fixture
    def router(self) -> MCPRouter:
        """Create a fresh router."""
        return MCPRouter()

    @pytest.fixture
    def prefixed_router(self) -> MCPRouter:
        """Create a router with prefix."""
        return MCPRouter(prefix="test.")

    def test_tool_registration(self, router: MCPRouter):
        """Test registering a tool."""

        @router.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        tools = router.get_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "add"
        assert "Add two numbers" in tools[0]["description"]

    def test_tool_with_custom_name(self, router: MCPRouter):
        """Test registering a tool with custom name."""

        @router.tool(name="custom_add", description="Custom addition")
        def add(a: int, b: int) -> int:
            return a + b

        tools = router.get_tools()
        assert tools[0]["name"] == "custom_add"
        assert tools[0]["description"] == "Custom addition"

    def test_tool_with_prefix(self, prefixed_router: MCPRouter):
        """Test tool registration with prefix."""

        @prefixed_router.tool()
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        tools = prefixed_router.get_tools()
        assert tools[0]["name"] == "test.multiply"

    def test_tool_input_schema(self, router: MCPRouter):
        """Test tool input schema generation."""

        @router.tool()
        def greet(name: str, count: int = 1) -> str:
            """Generate greeting."""
            return f"Hello, {name}!" * count

        tools = router.get_tools()
        schema = tools[0]["inputSchema"]

        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert "name" in schema["required"]
        assert "count" not in schema["required"]

    def test_resource_registration(self, router: MCPRouter):
        """Test registering a resource."""

        @router.resource("config://settings")
        def get_settings() -> dict:
            """Get application settings."""
            return {"theme": "dark"}

        resources = router.get_resources()
        assert len(resources) == 1
        assert resources[0]["uri"] == "config://settings"
        assert resources[0]["mimeType"] == "application/json"

    def test_resource_with_uri_params(self, router: MCPRouter):
        """Test registering a resource with URI parameters."""

        @router.resource("user://{user_id}")
        def get_user(user_id: str) -> dict:
            """Get user by ID."""
            return {"id": user_id, "name": f"User {user_id}"}

        resources = router.get_resources()
        assert resources[0]["uri"] == "user://{user_id}"

    def test_prompt_registration(self, router: MCPRouter):
        """Test registering a prompt."""

        @router.prompt()
        def code_review(code: str, language: str = "python") -> str:
            """Generate code review prompt."""
            return f"Review this {language} code:\n{code}"

        prompts = router.get_prompts()
        assert len(prompts) == 1
        assert prompts[0]["name"] == "code_review"
        assert len(prompts[0]["arguments"]) == 2

    def test_prompt_arguments(self, router: MCPRouter):
        """Test prompt argument extraction."""

        @router.prompt()
        def summarize(text: str, max_length: int = 100) -> str:
            """Summarize text."""
            return f"Summarize in {max_length} chars: {text}"

        prompts = router.get_prompts()
        args = prompts[0]["arguments"]

        text_arg = next(a for a in args if a["name"] == "text")
        max_arg = next(a for a in args if a["name"] == "max_length")

        assert text_arg["required"] is True
        assert max_arg["required"] is False

    @pytest.mark.asyncio
    async def test_call_tool(self, router: MCPRouter):
        """Test calling a tool."""

        @router.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        result = await router.call_tool("add", {"a": 5, "b": 3})
        assert result == 8

    @pytest.mark.asyncio
    async def test_call_async_tool(self, router: MCPRouter):
        """Test calling an async tool."""

        @router.tool()
        async def async_add(a: int, b: int) -> int:
            """Add two numbers asynchronously."""
            return a + b

        result = await router.call_tool("async_add", {"a": 10, "b": 20})
        assert result == 30

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self, router: MCPRouter):
        """Test calling a nonexistent tool."""
        with pytest.raises(ValueError, match="Tool not found"):
            await router.call_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_read_resource(self, router: MCPRouter):
        """Test reading a resource."""

        @router.resource("data://items")
        def get_items() -> list:
            """Get all items."""
            return [1, 2, 3]

        content, mime_type = await router.read_resource("data://items")
        assert content == [1, 2, 3]
        assert mime_type == "application/json"

    @pytest.mark.asyncio
    async def test_read_resource_with_params(self, router: MCPRouter):
        """Test reading a resource with URI parameters."""

        @router.resource("item://{item_id}")
        def get_item(item_id: str) -> dict:
            """Get item by ID."""
            return {"id": item_id}

        content, _ = await router.read_resource("item://123")
        assert content["id"] == "123"

    @pytest.mark.asyncio
    async def test_read_nonexistent_resource(self, router: MCPRouter):
        """Test reading a nonexistent resource."""
        with pytest.raises(ValueError, match="Resource not found"):
            await router.read_resource("nonexistent://resource")

    @pytest.mark.asyncio
    async def test_get_prompt_content(self, router: MCPRouter):
        """Test getting prompt content."""

        @router.prompt()
        def greeting(name: str) -> str:
            """Generate greeting prompt."""
            return f"Write a greeting for {name}"

        content = await router.get_prompt_content("greeting", {"name": "Alice"})
        assert "Alice" in content

    @pytest.mark.asyncio
    async def test_get_nonexistent_prompt(self, router: MCPRouter):
        """Test getting nonexistent prompt."""
        with pytest.raises(ValueError, match="Prompt not found"):
            await router.get_prompt_content("nonexistent", {})

    def test_include_router(self, router: MCPRouter):
        """Test including another router."""
        other = MCPRouter(prefix="other.")

        @other.tool()
        def other_tool() -> str:
            """Other tool."""
            return "other"

        @router.tool()
        def main_tool() -> str:
            """Main tool."""
            return "main"

        router.include_router(other)

        tools = router.get_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert "main_tool" in names
        assert "other.other_tool" in names

    def test_get_specific_tool(self, router: MCPRouter):
        """Test getting a specific tool definition."""

        @router.tool()
        def my_tool() -> str:
            """My tool."""
            return "result"

        tool = router.get_tool("my_tool")
        assert tool is not None
        assert tool.name == "my_tool"

        missing = router.get_tool("nonexistent")
        assert missing is None

    def test_get_specific_resource(self, router: MCPRouter):
        """Test getting a specific resource definition."""

        @router.resource("data://test")
        def my_resource() -> str:
            """My resource."""
            return "data"

        resource = router.get_resource("data://test")
        assert resource is not None
        assert resource.uri_template == "data://test"

    def test_get_specific_prompt(self, router: MCPRouter):
        """Test getting a specific prompt definition."""

        @router.prompt()
        def my_prompt() -> str:
            """My prompt."""
            return "prompt"

        prompt = router.get_prompt("my_prompt")
        assert prompt is not None
        assert prompt.name == "my_prompt"

    def test_uri_template_matching(self, router: MCPRouter):
        """Test URI template matching logic."""
        # Test simple template
        result = router._match_uri_template("user://{id}", "user://123")
        assert result == {"id": "123"}

        # Test multiple params
        result = router._match_uri_template(
            "org://{org}/repo://{repo}",
            "org://acme/repo://project"
        )
        assert result == {"org": "acme", "repo": "project"}

        # Test no match
        result = router._match_uri_template("user://{id}", "other://123")
        assert result is None
