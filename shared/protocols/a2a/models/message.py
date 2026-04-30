"""
A2A Message Models

Defines Message and Part types for agent communication.
Based on Google's A2A Protocol Specification v0.3.0
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID


class FileContent(BaseModel):
    """File content that can be inline (bytes) or referenced (uri)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="File name")
    mime_type: str = Field(..., alias="mimeType", description="MIME type of the file")
    # Either bytes (base64) or uri, not both
    bytes: str | None = Field(default=None, description="Base64-encoded file content")
    uri: str | None = Field(default=None, description="URI reference to the file")
    size_bytes: int | None = Field(default=None, alias="sizeBytes", description="File size in bytes")


class TextPart(BaseModel):
    """Text content part."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    text: str = Field(..., description="The text content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Part-specific metadata")


class FilePart(BaseModel):
    """File content part."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["file"] = "file"
    file: FileContent = Field(..., description="The file content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Part-specific metadata")


class DataPart(BaseModel):
    """Structured JSON data part."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["data"] = "data"
    data: dict[str, Any] = Field(..., description="Structured JSON data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Part-specific metadata")


# Union type for parts
Part = TextPart | FilePart | DataPart


class Message(BaseModel):
    """
    A message in an A2A conversation.

    Messages are exchanged between agents as part of task execution.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message_id: str = Field(
        default_factory=lambda: f"msg_{ULID()}",
        alias="messageId",
        description="Unique message identifier",
    )
    role: Literal["user", "agent"] = Field(..., description="Role of the message sender")
    parts: Sequence[Part] = Field(..., description="Content parts of the message")

    # Context references
    task_id: str | None = Field(default=None, alias="taskId", description="Associated task ID")
    context_id: str | None = Field(default=None, alias="contextId", description="Conversation context ID")

    # Timing
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Message timestamp"
    )

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional message metadata"
    )

    @classmethod
    def text(
        cls,
        text: str,
        role: Literal["user", "agent"] = "user",
        task_id: str | None = None,
        context_id: str | None = None,
    ) -> "Message":
        """Convenience factory for creating a simple text message."""
        return cls(
            role=role,
            parts=[TextPart(text=text)],
            task_id=task_id,  # type: ignore[call-arg]
            context_id=context_id,  # type: ignore[call-arg]
        )

    @classmethod
    def data(
        cls,
        data: dict[str, Any],
        role: Literal["user", "agent"] = "agent",
        task_id: str | None = None,
        context_id: str | None = None,
    ) -> "Message":
        """Convenience factory for creating a structured data message."""
        return cls(
            role=role,
            parts=[DataPart(data=data)],
            task_id=task_id,  # type: ignore[call-arg]
            context_id=context_id,  # type: ignore[call-arg]
        )

    def get_text_content(self) -> str | None:
        """Extract text content from message parts."""
        text_parts = [part.text for part in self.parts if isinstance(part, TextPart)]
        return "\n".join(text_parts) if text_parts else None

    def get_data_content(self) -> dict[str, Any] | None:
        """Extract data content from message parts."""
        for part in self.parts:
            if isinstance(part, DataPart):
                return part.data
        return None


class MessageSendParams(BaseModel):
    """Parameters for the message/send JSON-RPC method."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


    message: Message = Field(..., description="The message to send")
    context_id: str | None = Field(
        default=None,
        alias="contextId",
        description="Existing context to continue, or None for new context",
    )
    # Configuration
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Task configuration parameters"
    )
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
