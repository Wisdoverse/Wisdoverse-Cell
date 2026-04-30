"""
A2A Protocol Models

Pydantic models for A2A protocol entities.
"""

from .agent_card import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    SecurityScheme,
)
from .message import (
    DataPart,
    FileContent,
    FilePart,
    Message,
    MessageSendParams,
    Part,
    TextPart,
)
from .task import (
    Artifact,
    PushNotificationConfig,
    Task,
    TaskCancelParams,
    TaskGetParams,
    TaskState,
    TaskStatus,
)

__all__ = [
    # Agent Card
    "AgentCard",
    "AgentCapabilities",
    "AgentInterface",
    "AgentProvider",
    "AgentSkill",
    "SecurityScheme",
    # Message
    "DataPart",
    "FileContent",
    "FilePart",
    "Message",
    "MessageSendParams",
    "Part",
    "TextPart",
    # Task
    "Artifact",
    "PushNotificationConfig",
    "Task",
    "TaskCancelParams",
    "TaskGetParams",
    "TaskState",
    "TaskStatus",
]
