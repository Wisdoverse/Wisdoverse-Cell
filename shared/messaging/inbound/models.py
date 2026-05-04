"""
Gateway models for cross-platform unified messaging.

Defines message abstractions for unified handling across Feishu, WeCom, Web,
and other platforms.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from shared.models.platform import Platform


class MessageType(str, Enum):
    """Message type."""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    POST = "post"  # Rich text.
    CARD = "card"


class CardActionStyle(str, Enum):
    """Card button style."""

    PRIMARY = "primary"  # Blue.
    DANGER = "danger"  # Red.
    DEFAULT = "default"  # Gray.


class UnifiedMessage(BaseModel):
    """Unified inbound message across platforms."""

    # Source.
    platform: Platform
    message_id: str

    # Conversation.
    chat_id: str
    chat_type: str = "private"  # "private" / "group"

    # Sender.
    sender_id: str
    sender_name: str = ""
    user_id: Optional[str] = None  # Unified user ID, filled after mapping.

    # Content.
    message_type: MessageType = MessageType.TEXT
    content: str = ""
    mentions: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)

    # Time.
    timestamp: datetime

    # Raw data.
    raw_data: dict = Field(default_factory=dict, exclude=True)


class CardAction(BaseModel):
    """Card action button."""

    label: str
    action_id: str
    value: dict = Field(default_factory=dict)
    style: CardActionStyle = CardActionStyle.DEFAULT


class UnifiedCard(BaseModel):
    """Unified outbound card across platforms."""

    title: str
    content: str  # Markdown

    # State.
    status: Optional[str] = None
    status_color: Optional[str] = None  # "orange" / "green" / "red"
    priority: Optional[str] = None

    # Fields.
    fields: list[dict] = Field(default_factory=list)  # Example: [{"label": "Category", "value": "Feature"}].

    # Buttons.
    actions: list[CardAction] = Field(default_factory=list)

    # Context.
    context: dict = Field(default_factory=dict)


class UnifiedAction(BaseModel):
    """Unified callback action across platforms."""

    platform: Platform
    action_id: str
    message_id: str

    # Operator.
    operator_id: str
    user_id: Optional[str] = None

    # Data.
    value: dict = Field(default_factory=dict)
    raw_data: dict = Field(default_factory=dict, exclude=True)


class AgentResponse(BaseModel):
    """Agent response."""

    text: Optional[str] = None
    card: Optional[UnifiedCard] = None
    update_card: bool = False


class ActionResponse(BaseModel):
    """Action handling response."""

    update_card: bool = False
    card: Optional[UnifiedCard] = None
    toast: Optional[str] = None
