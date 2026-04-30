# shared/services/channels/base.py
"""
MessageChannel - 消息渠道抽象基类

定义所有消息渠道必须实现的接口。
"""
from abc import ABC, abstractmethod

from .types import ChannelCard, ChannelMessage, ChannelResponse


class MessageChannel(ABC):
    """
    消息渠道抽象接口

    所有渠道（飞书、企微等）必须实现此接口。
    Agent 层通过此接口发送消息，不感知具体渠道。
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """
        渠道标识

        Returns:
            渠道名称，如 "feishu" 或 "wecom"
        """
        ...

    @abstractmethod
    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """
        发送文本/Markdown 消息

        Args:
            user_id: 接收者 ID（格式取决于具体渠道）
            content: 消息内容

        Returns:
            消息 ID
        """
        ...

    @abstractmethod
    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        """
        发送卡片消息

        Args:
            user_id: 接收者 ID
            card: 通用卡片

        Returns:
            消息 ID
        """
        ...

    @abstractmethod
    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """
        更新已发送的卡片

        Args:
            message_id: 要更新的消息 ID
            card: 新卡片内容

        Returns:
            是否更新成功
        """
        ...

    @abstractmethod
    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """
        处理回调（消息/按钮）

        Args:
            payload: 回调数据

        Returns:
            处理结果
        """
        ...
