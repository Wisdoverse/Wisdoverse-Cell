"""
Notification Service - 统一的通知服务

支持多渠道通知:
- 飞书 (API)
- 邮件 (未实现)
- 短信 (未实现)
"""
from enum import Enum
from typing import Optional

from ..config import settings
from ..utils.logger import get_logger

logger = get_logger("notification")


class NotificationChannel(Enum):
    """通知渠道"""
    FEISHU = "feishu"
    EMAIL = "email"
    SMS = "sms"


class NotificationService:
    """
    通知服务

    使用方式:
        notifier = NotificationService()
        await notifier.send(
            channel=NotificationChannel.FEISHU,
            title="新需求待确认",
            content="从会议中提取了3个新需求",
            link="http://localhost:8000/requirements"
        )
    """

    def __init__(self):
        self._feishu_client = None

    def _get_feishu_client(self):
        """延迟初始化飞书客户端"""
        if self._feishu_client is None:
            from shared.integrations.feishu.client import get_feishu_client
            self._feishu_client = get_feishu_client()
        return self._feishu_client

    async def send(
        self,
        channel: NotificationChannel,
        title: str,
        content: str,
        link: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        发送通知

        Args:
            channel: 通知渠道
            title: 标题
            content: 内容
            link: 可选的链接
            **kwargs: 渠道特定的参数

        Returns:
            是否发送成功
        """
        handlers = {
            NotificationChannel.FEISHU: lambda: self._send_feishu(title, content, link),
            NotificationChannel.EMAIL: lambda: self._send_email(title, content, **kwargs),
            NotificationChannel.SMS: lambda: self._send_sms(content, **kwargs),
        }

        handler = handlers.get(channel)
        if handler:
            return await handler()

        logger.warning("unknown_notification_channel", channel=channel.value)
        return False

    async def _send_feishu(
        self,
        title: str,
        content: str,
        link: Optional[str] = None
    ) -> bool:
        """发送飞书消息（使用 API）"""
        if not settings.feishu_enabled:
            logger.warning("feishu_not_enabled")
            return False

        # 优先发送给个人用户，其次发送到群聊
        if settings.feishu_default_user_id:
            receive_id = settings.feishu_default_user_id
            receive_id_type = "open_id"
        elif settings.feishu_default_chat_id:
            receive_id = settings.feishu_default_chat_id
            receive_id_type = "chat_id"
        else:
            logger.warning("feishu_no_recipient_configured")
            return False

        # 构建消息卡片
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": content
                }
            }
        ]

        # 添加链接按钮
        if link:
            elements.append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "查看详情"
                        },
                        "type": "primary",
                        "url": link
                    }
                ]
            })

        card = {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": elements
        }

        try:
            client = self._get_feishu_client()
            await client.send_card(
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                card=card
            )
            logger.info("feishu_notification_sent", title=title, receive_id=receive_id)
            return True

        except Exception as e:
            logger.error("feishu_notification_failed", error=str(e))
            return False

    async def _send_email(self, title: str, content: str, **kwargs) -> bool:
        """发送邮件（未实现）"""
        logger.warning("email_notification_not_implemented")
        return False

    async def _send_sms(self, content: str, **kwargs) -> bool:
        """发送短信（未实现）"""
        logger.warning("sms_notification_not_implemented")
        return False


# 全局通知服务实例
notification_service = NotificationService()
