"""
BasePlatformAdapter - 平台适配器抽象基类

所有平台适配器必须实现此接口，提供统一的消息处理能力。
"""

from abc import ABC, abstractmethod
from typing import Optional

from .models import Platform, UnifiedAction, UnifiedCard, UnifiedMessage


class BasePlatformAdapter(ABC):
    """
    平台适配器基类

    职责：
    1. 将平台原始消息转换为 UnifiedMessage
    2. 将 UnifiedCard 转换为平台卡片格式
    3. 将平台回调转换为 UnifiedAction
    4. 发送消息到平台
    5. 获取用户信息用于身份映射
    """

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """返回适配器对应的平台"""
        pass

    @abstractmethod
    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        将平台原始消息事件转换为统一格式

        Args:
            raw_event: 平台原始事件数据

        Returns:
            UnifiedMessage 或 None（如果无法解析）
        """
        pass

    @abstractmethod
    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        """
        将平台卡片回调转换为统一操作

        Args:
            raw_callback: 平台回调数据

        Returns:
            UnifiedAction 或 None（如果无法解析）
        """
        pass

    @abstractmethod
    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        """
        发送卡片消息

        Args:
            chat_id: 会话 ID
            card: 统一卡片格式

        Returns:
            平台消息 ID
        """
        pass

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> str:
        """
        发送文本消息

        Args:
            chat_id: 会话 ID
            text: 文本内容

        Returns:
            平台消息 ID
        """
        pass

    @abstractmethod
    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        """
        更新已发送的卡片

        Args:
            message_id: 要更新的消息 ID
            card: 新的卡片内容

        Returns:
            是否更新成功
        """
        pass

    @abstractmethod
    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        """
        获取用户邮箱（用于跨平台身份映射）

        Args:
            platform_user_id: 平台用户 ID

        Returns:
            用户邮箱或 None
        """
        pass

    @abstractmethod
    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        获取用户名称

        Args:
            platform_user_id: 平台用户 ID

        Returns:
            用户名称或 None
        """
        pass

    def build_platform_card(self, card: UnifiedCard) -> dict:
        """Convert UnifiedCard to platform-native card format.

        Default raises NotImplementedError. Subclasses that support
        cards should override. Replaces hasattr anti-pattern.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement build_platform_card"
        )
