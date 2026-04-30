"""
A2A Task Models

Defines Task, TaskState, and Artifact models for task management.
Based on Google's A2A Protocol Specification v0.3.0
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from .message import Message, Part


class TaskStatus(str, Enum):
    """Possible states for a task."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskState(BaseModel):
    """Current state of a task."""

    model_config = ConfigDict(extra="forbid")

    state: TaskStatus = Field(..., description="Current task state")
    message: Message | None = Field(default=None, description="Status message from the agent")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When the state changed"
    )

    @classmethod
    def submitted(cls) -> "TaskState":
        """Create a submitted state."""
        return cls(state=TaskStatus.SUBMITTED)

    @classmethod
    def working(cls, message: str | None = None) -> "TaskState":
        """Create a working state with optional status message."""
        msg = (
            Message.text(message, role="agent")
            if message
            else None
        )
        return cls(state=TaskStatus.WORKING, message=msg)

    @classmethod
    def input_required(cls, prompt: str) -> "TaskState":
        """Create an input-required state with prompt."""
        return cls(
            state=TaskStatus.INPUT_REQUIRED,
            message=Message.text(prompt, role="agent"),
        )

    @classmethod
    def completed(cls, message: str | None = None) -> "TaskState":
        """Create a completed state with optional message."""
        msg = (
            Message.text(message, role="agent")
            if message
            else None
        )
        return cls(state=TaskStatus.COMPLETED, message=msg)

    @classmethod
    def failed(cls, error: str) -> "TaskState":
        """Create a failed state with error message."""
        return cls(
            state=TaskStatus.FAILED,
            message=Message.text(error, role="agent"),
        )

    @classmethod
    def canceled(cls, reason: str | None = None) -> "TaskState":
        """Create a canceled state with optional reason."""
        msg = (
            Message.text(reason, role="agent")
            if reason
            else None
        )
        return cls(state=TaskStatus.CANCELED, message=msg)


class Artifact(BaseModel):
    """
    An artifact produced by a task.

    Artifacts are the outputs of task execution (files, data, etc.)
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str = Field(
        default_factory=lambda: f"art_{ULID()}",
        alias="artifactId",
        description="Unique artifact identifier",
    )
    name: str = Field(..., description="Human-readable name of the artifact")
    description: str | None = Field(default=None, description="Description of the artifact")
    parts: list[Part] = Field(..., description="Content parts of the artifact")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Artifact metadata")


class Task(BaseModel):
    """
    An A2A Task represents a unit of work being performed by an agent.

    Tasks are created when a message is sent to an agent and track the
    progress of the work through various states until completion.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Identity
    id: str = Field(
        default_factory=lambda: f"task_{ULID()}", description="Unique task identifier"
    )
    context_id: str = Field(
        default_factory=lambda: f"ctx_{ULID()}",
        alias="contextId",
        description="Conversation context identifier",
    )

    # State
    status: TaskState = Field(
        default_factory=TaskState.submitted, description="Current task state"
    )

    # Content
    artifacts: list[Artifact] = Field(
        default_factory=list, description="Artifacts produced by the task"
    )
    history: list[Message] = Field(
        default_factory=list, description="Conversation history for this task"
    )

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Task metadata")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="createdAt",
        description="Task creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="updatedAt",
        description="Task last update timestamp",
    )

    # Type discriminator for union types
    kind: str = Field(default="task", description="Object type discriminator")

    def update_status(self, new_state: TaskState) -> None:
        """Update task status and timestamp."""
        self.status = new_state
        self.updated_at = datetime.now(UTC)

    def add_message(self, message: Message) -> None:
        """Add a message to the task history."""
        message.task_id = self.id
        message.context_id = self.context_id
        self.history.append(message)
        self.updated_at = datetime.now(UTC)

    def add_artifact(self, artifact: Artifact) -> None:
        """Add an artifact to the task."""
        self.artifacts.append(artifact)
        self.updated_at = datetime.now(UTC)

    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status.state in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELED,
        )


class TaskGetParams(BaseModel):
    """Parameters for the tasks/get JSON-RPC method."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str = Field(..., alias="taskId", description="ID of the task to retrieve")
    history_length: int | None = Field(
        default=None, alias="historyLength", description="Max history messages to return"
    )


class TaskCancelParams(BaseModel):
    """Parameters for the tasks/cancel JSON-RPC method."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str = Field(..., alias="taskId", description="ID of the task to cancel")
    reason: str | None = Field(default=None, description="Reason for cancellation")


class PushNotificationConfig(BaseModel):
    """Configuration for push notifications."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str = Field(..., alias="taskId", description="Task ID to configure notifications for")
    webhook_url: str = Field(
        ..., alias="webhookUrl", description="URL to receive push notifications"
    )
    events: list[str] = Field(
        default_factory=lambda: ["status_changed"],
        description="Events to notify on",
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Custom headers for webhook requests"
    )
