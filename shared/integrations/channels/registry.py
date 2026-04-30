# shared/services/channels/registry.py
"""
ChannelRegistry - 渠道注册表

管理所有消息渠道的注册和获取。
"""
from threading import Lock

from .base import MessageChannel


class ChannelRegistry:
    """
    渠道注册表 - 管理所有消息渠道

    使用方式:
        # 注册渠道
        ChannelRegistry.register(feishu_channel)
        ChannelRegistry.register(wecom_channel)

        # 获取渠道
        channel = ChannelRegistry.get("feishu")
        await channel.send_message(user_id, message)
    """

    _channels: dict[str, MessageChannel] = {}
    _lock = Lock()

    @classmethod
    def register(cls, channel: MessageChannel) -> None:
        """
        注册渠道

        Args:
            channel: 渠道实例
        """
        with cls._lock:
            cls._channels[channel.channel_name] = channel

    @classmethod
    def get(cls, name: str) -> MessageChannel | None:
        """
        获取渠道

        Args:
            name: 渠道名称

        Returns:
            渠道实例，不存在时返回 None
        """
        with cls._lock:
            return cls._channels.get(name)

    @classmethod
    def all(cls) -> dict[str, MessageChannel]:
        """
        获取所有渠道

        Returns:
            渠道字典的副本
        """
        with cls._lock:
            return cls._channels.copy()

    @classmethod
    def clear(cls) -> None:
        """清空所有注册的渠道（用于测试）"""
        with cls._lock:
            cls._channels.clear()
