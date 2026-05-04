"""Shared channel message and card value objects."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChannelMessage(BaseModel):
    """Text or Markdown message sent through a channel adapter."""

    model_config = ConfigDict(frozen=True)

    content: str
    message_type: Literal["text", "markdown"] = "text"


class CardElement(BaseModel):
    """Portable card element."""

    model_config = ConfigDict(frozen=True)

    element_type: Literal["text", "field", "divider"]
    content: str | None = None
    fields: list[dict] | None = None


class CardAction(BaseModel):
    """Portable card action."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    label: str
    style: Literal["primary", "danger", "default"] = "default"
    payload: dict = Field(default_factory=dict)


class ChannelCard(BaseModel):
    """Portable card sent through a channel adapter."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    title: str
    elements: list[CardElement]
    actions: list[CardAction]


class IncomingMessage(BaseModel):
    """Normalized inbound channel message."""

    model_config = ConfigDict(frozen=True)

    channel: Literal["feishu", "wecom"]
    user_id: str
    user_name: str | None = None
    message_id: str
    content: str
    message_type: Literal["text", "file", "image", "card_action"]
    timestamp: datetime
    raw: dict


class ChannelResponse(BaseModel):
    """Normalized channel callback response."""

    model_config = ConfigDict(frozen=True)

    success: bool
    message: str | None = None
    data: dict | None = None
