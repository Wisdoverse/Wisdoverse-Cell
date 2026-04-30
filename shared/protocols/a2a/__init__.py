"""
A2A (Agent-to-Agent) Protocol Implementation

Google's open protocol for agent-to-agent communication.
Supports JSON-RPC transport with streaming via SSE.
"""

from .models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    Message,
    Task,
    TaskState,
    TaskStatus,
)

__all__ = [
    # Models
    "AgentCapabilities",
    "AgentCard",
    "AgentSkill",
    "Artifact",
    "Message",
    "Task",
    "TaskState",
    "TaskStatus",
]
