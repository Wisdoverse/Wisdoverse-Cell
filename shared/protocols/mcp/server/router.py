"""
MCP Router

FastAPI-style router for MCP tools, resources, and prompts.
Inspired by the FastMCP interface.
"""

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict, Field


class ToolDefinition(BaseModel):
    """MCP Tool definition."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_schema: dict[str, Any] = Field(..., description="JSON Schema for inputs")
    handler: Callable = Field(..., exclude=True, description="Handler function")


class ResourceDefinition(BaseModel):
    """MCP Resource definition."""

    model_config = ConfigDict(extra="forbid")

    uri_template: str = Field(..., description="URI template (e.g., 'user://{id}')")
    name: str = Field(..., description="Resource name")
    description: str = Field(..., description="Resource description")
    mime_type: str = Field("application/json", description="MIME type")
    handler: Callable = Field(..., exclude=True, description="Handler function")


class PromptDefinition(BaseModel):
    """MCP Prompt definition."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Prompt name")
    description: str = Field(..., description="Prompt description")
    arguments: list[dict[str, Any]] = Field(
        default_factory=list, description="Prompt arguments"
    )
    handler: Callable = Field(..., exclude=True, description="Handler function")


def _get_json_schema_type(python_type: type) -> dict[str, Any]:
    """Convert Python type to JSON Schema type."""
    type_mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
        type(None): {"type": "null"},
    }

    # Handle generic types
    origin = getattr(python_type, "__origin__", None)
    if origin is list:
        args = getattr(python_type, "__args__", (Any,))
        return {
            "type": "array",
            "items": _get_json_schema_type(args[0]) if args else {},
        }
    if origin is dict:
        return {"type": "object"}

    # Handle Union types (Optional)
    if origin is type(str | None):  # Union
        args = getattr(python_type, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _get_json_schema_type(non_none[0])
        return {"anyOf": [_get_json_schema_type(a) for a in non_none]}

    return type_mapping.get(python_type, {"type": "string"})


def _function_to_json_schema(func: Callable) -> dict[str, Any]:
    """Generate JSON Schema from function signature."""
    sig = inspect.signature(func)
    hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        prop = {}
        if name in hints:
            prop = _get_json_schema_type(hints[name])

        # Add description from docstring if available
        if func.__doc__:
            # Simple extraction - could be improved
            prop["description"] = f"Parameter: {name}"

        properties[name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class MCPRouter:
    """
    MCP Router for registering tools, resources, and prompts.

    Usage:
        router = MCPRouter(prefix="myagent.")

        @router.tool()
        async def my_tool(arg1: str, arg2: int = 10) -> dict:
            '''My tool description.'''
            return {"result": arg1 * arg2}

        @router.resource("data://{id}")
        async def get_data(id: str) -> dict:
            '''Get data by ID.'''
            return {"id": id}

        @router.prompt()
        async def my_prompt(topic: str) -> str:
            '''Generate a prompt about a topic.'''
            return f"Write about {topic}"
    """

    def __init__(self, prefix: str = ""):
        """
        Initialize MCP Router.

        Args:
            prefix: Prefix for all tool/resource names.
        """
        self._prefix = prefix
        self._tools: dict[str, ToolDefinition] = {}
        self._resources: dict[str, ResourceDefinition] = {}
        self._prompts: dict[str, PromptDefinition] = {}

    @property
    def prefix(self) -> str:
        """Get the router prefix."""
        return self._prefix

    def _get_name(self, func: Callable, name: str | None = None) -> str:
        """Get prefixed name for a function."""
        base_name = name or func.__name__
        return f"{self._prefix}{base_name}" if self._prefix else base_name

    # ============ Tool Decorator ============

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable:
        """
        Decorator to register a function as an MCP tool.

        Args:
            name: Optional tool name (defaults to function name).
            description: Optional description (defaults to docstring).

        Returns:
            Decorator function.

        Example:
            @router.tool()
            async def search(query: str, limit: int = 10) -> list[dict]:
                '''Search for items.'''
                ...
        """

        def decorator(func: Callable) -> Callable:
            tool_name = self._get_name(func, name)
            tool_desc = description or func.__doc__ or f"Tool: {tool_name}"
            input_schema = _function_to_json_schema(func)

            self._tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_desc.strip(),
                input_schema=input_schema,
                handler=func,
            )

            @wraps(func)
            async def wrapper(*args, **kwargs):
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            return wrapper

        return decorator

    # ============ Resource Decorator ============

    def resource(
        self,
        uri_template: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str = "application/json",
    ) -> Callable:
        """
        Decorator to register a function as an MCP resource.

        Args:
            uri_template: URI template (e.g., "user://{id}").
            name: Optional resource name.
            description: Optional description.
            mime_type: Content MIME type.

        Returns:
            Decorator function.

        Example:
            @router.resource("config://settings")
            async def get_settings() -> dict:
                '''Get application settings.'''
                ...
        """

        def decorator(func: Callable) -> Callable:
            resource_name = self._get_name(func, name)
            resource_desc = description or func.__doc__ or f"Resource: {resource_name}"

            self._resources[uri_template] = ResourceDefinition(
                uri_template=uri_template,
                name=resource_name,
                description=resource_desc.strip(),
                mime_type=mime_type,
                handler=func,
            )

            @wraps(func)
            async def wrapper(*args, **kwargs):
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            return wrapper

        return decorator

    # ============ Prompt Decorator ============

    def prompt(
        self,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable:
        """
        Decorator to register a function as an MCP prompt.

        Args:
            name: Optional prompt name.
            description: Optional description.

        Returns:
            Decorator function.

        Example:
            @router.prompt()
            async def code_review(code: str) -> str:
                '''Generate a code review prompt.'''
                return f"Please review this code:\\n{code}"
        """

        def decorator(func: Callable) -> Callable:
            prompt_name = self._get_name(func, name)
            prompt_desc = description or func.__doc__ or f"Prompt: {prompt_name}"

            # Extract arguments from function signature
            sig = inspect.signature(func)
            hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

            arguments = []
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue

                arg = {
                    "name": param_name,
                    "required": param.default is inspect.Parameter.empty,
                }

                if param_name in hints:
                    schema = _get_json_schema_type(hints[param_name])
                    arg.update(schema)

                arguments.append(arg)

            self._prompts[prompt_name] = PromptDefinition(
                name=prompt_name,
                description=prompt_desc.strip(),
                arguments=arguments,
                handler=func,
            )

            @wraps(func)
            async def wrapper(*args, **kwargs):
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            return wrapper

        return decorator

    # ============ Getters ============

    def get_tools(self) -> list[dict[str, Any]]:
        """Get all registered tools in MCP format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def get_resources(self) -> list[dict[str, Any]]:
        """Get all registered resources in MCP format."""
        return [
            {
                "uri": resource.uri_template,
                "name": resource.name,
                "description": resource.description,
                "mimeType": resource.mime_type,
            }
            for resource in self._resources.values()
        ]

    def get_prompts(self) -> list[dict[str, Any]]:
        """Get all registered prompts in MCP format."""
        return [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments,
            }
            for prompt in self._prompts.values()
        ]

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a specific tool by name."""
        return self._tools.get(name)

    def get_resource(self, uri_template: str) -> ResourceDefinition | None:
        """Get a specific resource by URI template."""
        return self._resources.get(uri_template)

    def get_prompt(self, name: str) -> PromptDefinition | None:
        """Get a specific prompt by name."""
        return self._prompts.get(name)

    # ============ Execution ============

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        Call a registered tool.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result.

        Raises:
            ValueError: If tool not found.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Tool not found: {name}")

        args = arguments or {}
        if inspect.iscoroutinefunction(tool.handler):
            return await tool.handler(**args)
        return tool.handler(**args)

    async def read_resource(
        self,
        uri: str,
    ) -> tuple[Any, str]:
        """
        Read a registered resource.

        Args:
            uri: Resource URI.

        Returns:
            Tuple of (content, mime_type).

        Raises:
            ValueError: If resource not found.
        """
        # Find matching resource
        for template, resource in self._resources.items():
            params = self._match_uri_template(template, uri)
            if params is not None:
                if inspect.iscoroutinefunction(resource.handler):
                    content = await resource.handler(**params)
                else:
                    content = resource.handler(**params)
                return content, resource.mime_type

        raise ValueError(f"Resource not found: {uri}")

    async def get_prompt_content(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """
        Get content for a prompt.

        Args:
            name: Prompt name.
            arguments: Prompt arguments.

        Returns:
            Prompt content string.

        Raises:
            ValueError: If prompt not found.
        """
        prompt = self._prompts.get(name)
        if prompt is None:
            raise ValueError(f"Prompt not found: {name}")

        args = arguments or {}
        if inspect.iscoroutinefunction(prompt.handler):
            return await prompt.handler(**args)
        return prompt.handler(**args)

    def _match_uri_template(
        self,
        template: str,
        uri: str,
    ) -> dict[str, str] | None:
        """
        Match a URI against a template and extract parameters.

        Args:
            template: URI template (e.g., "user://{id}").
            uri: Actual URI to match.

        Returns:
            Dictionary of extracted parameters or None if no match.
        """
        import re

        # Convert template to regex
        # Replace {param} with named capture group
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", template)
        pattern = f"^{pattern}$"

        match = re.match(pattern, uri)
        if match:
            return match.groupdict()
        return None

    # ============ Merging ============

    def include_router(self, router: "MCPRouter") -> None:
        """
        Include another router's definitions.

        Args:
            router: Router to include.
        """
        self._tools.update(router._tools)
        self._resources.update(router._resources)
        self._prompts.update(router._prompts)
