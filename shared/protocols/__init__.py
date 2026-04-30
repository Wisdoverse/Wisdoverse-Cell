"""
Protocols - A2A and MCP protocol implementations

This package provides standardized protocol support for agent communication:
- A2A (Agent-to-Agent): Google's agent communication protocol
- MCP (Model Context Protocol): Anthropic's tool calling protocol
- Bridge: Protocol adapters for EventBus integration
"""

from .a2a import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    Message,
    Task,
    TaskState,
    TaskStatus,
)
from .bridge import EventBusA2ABridge
from .mcp import MCPRouter, MCPServer

__all__ = [
    # A2A
    "AgentCapabilities",
    "AgentCard",
    "AgentSkill",
    "Artifact",
    "Message",
    "Task",
    "TaskState",
    "TaskStatus",
    # MCP
    "MCPRouter",
    "MCPServer",
    # Bridge
    "EventBusA2ABridge",
]
