"""
MCP (Model Context Protocol) Implementation

Anthropic's protocol for tool calling and resource management.
Provides decorators for easy tool/resource registration.
"""

from .server.base import MCPServer
from .server.router import MCPRouter
from .server.routes import create_mcp_router, mount_mcp_routes

__all__ = [
    "MCPRouter",
    "MCPServer",
    "create_mcp_router",
    "mount_mcp_routes",
]
