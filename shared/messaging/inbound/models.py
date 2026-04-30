"""
Gateway Models - 跨平台统一消息模型

定义跨平台消息抽象，用于飞书、企微、Web 等平台的统一处理。
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from shared.models.platform import Platform


class MessageType(str, Enum):
    """消息类型"""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    POST = "post"  # 富文本
    CARD = "card"


class CardActionStyle(str, Enum):
    """卡片按钮样式"""

    PRIMARY = "primary"  # 蓝色
    DANGER = "danger"  # 红色
    DEFAULT = "default"  # 灰色


class UnifiedMessage(BaseModel):
    """跨平台统一入站消息"""

    # 来源
    platform: Platform
    message_id: str

    # 会话
    chat_id: str
    chat_type: str = "private"  # "private" / "group"

    # 发送者
    sender_id: str
    sender_name: str = ""
    user_id: Optional[str] = None  # 统一用户 ID (映射后填充)

    # 内容
    message_type: MessageType = MessageType.TEXT
    content: str = ""
    mentions: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)

    # 时间
    timestamp: datetime

    # 原始数据
    raw_data: dict = Field(default_factory=dict, exclude=True)


class CardAction(BaseModel):
    """卡片操作按钮"""

    label: str
    action_id: str
    value: dict = Field(default_factory=dict)
    style: CardActionStyle = CardActionStyle.DEFAULT


class UnifiedCard(BaseModel):
    """跨平台统一出站卡片"""

    title: str
    content: str  # Markdown

    # 状态
    status: Optional[str] = None
    status_color: Optional[str] = None  # "orange" / "green" / "red"
    priority: Optional[str] = None

    # 字段
    fields: list[dict] = Field(default_factory=list)  # [{"label": "分类", "value": "功能"}]

    # 按钮
    actions: list[CardAction] = Field(default_factory=list)

    # 上下文
    context: dict = Field(default_factory=dict)


class UnifiedAction(BaseModel):
    """跨平台统一回调操作"""

    platform: Platform
    action_id: str
    message_id: str

    # 操作者
    operator_id: str
    user_id: Optional[str] = None

    # 数据
    value: dict = Field(default_factory=dict)
    raw_data: dict = Field(default_factory=dict, exclude=True)


class AgentResponse(BaseModel):
    """Agent 响应"""

    text: Optional[str] = None
    card: Optional[UnifiedCard] = None
    update_card: bool = False


class ActionResponse(BaseModel):
    """Action 处理响应"""

    update_card: bool = False
    card: Optional[UnifiedCard] = None
    toast: Optional[str] = None
