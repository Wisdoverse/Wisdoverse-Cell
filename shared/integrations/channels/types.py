"""
Channel Types - 消息渠道通用类型

定义飞书和企微共用的消息类型。
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChannelMessage(BaseModel):
    """通用消息"""
    model_config = ConfigDict(frozen=True)

    content: str
    message_type: Literal["text", "markdown"] = "text"


class CardElement(BaseModel):
    """卡片元素"""
    model_config = ConfigDict(frozen=True)

    element_type: Literal["text", "field", "divider"]
    content: str | None = None
    fields: list[dict] | None = None


class CardAction(BaseModel):
    """卡片按钮"""
    model_config = ConfigDict(frozen=True)

    action_id: str
    label: str
    style: Literal["primary", "danger", "default"] = "default"
    payload: dict = Field(default_factory=dict)


class ChannelCard(BaseModel):
    """通用卡片"""
    model_config = ConfigDict(frozen=True)

    card_id: str
    title: str
    elements: list[CardElement]
    actions: list[CardAction]


class IncomingMessage(BaseModel):
    """收到的消息（统一格式）"""
    model_config = ConfigDict(frozen=True)

    channel: Literal["feishu", "wecom"]
    user_id: str
    user_name: str | None = None
    message_id: str
    content: str
    message_type: Literal["text", "file", "image", "card_action"]
    timestamp: datetime
    raw: dict  # 原始数据保留


class ChannelResponse(BaseModel):
    """回调处理结果"""
    model_config = ConfigDict(frozen=True)

    success: bool
    message: str | None = None
    data: dict | None = None
