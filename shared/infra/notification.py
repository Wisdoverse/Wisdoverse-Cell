"""
Notification Service - unified notification service.

Supports multi-channel notifications:
- Feishu (API)
- Email (not implemented)
- SMS (not implemented)
"""
from enum import Enum
from typing import Optional

from ..config import settings
from ..observability.privacy import hash_identifier
from ..utils.logger import get_logger

logger = get_logger("notification")


class NotificationChannel(Enum):
    """Notification channel."""
    FEISHU = "feishu"
    EMAIL = "email"
    SMS = "sms"


class NotificationService:
    """
    Notification service.

    Usage:
        notifier = NotificationService()
        await notifier.send(
            channel=NotificationChannel.FEISHU,
            title="New requirements need confirmation",
            content="Extracted three new requirements from the meeting",
            link="http://localhost:8000/requirements"
        )
    """

    def __init__(self):
        self._feishu_client = None

    def _get_feishu_client(self):
        """Lazily initialize the Feishu client."""
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
        Send a notification.

        Args:
            channel: Notification channel.
            title: Title.
            content: Content.
            link: Optional link.
            **kwargs: Channel-specific parameters.

        Returns:
            Whether the notification was sent successfully.
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
        """Send a Feishu message through the API."""
        if not settings.feishu_enabled:
            logger.warning("feishu_not_enabled")
            return False

        # Prefer sending to a direct user, then fall back to a chat.
        if settings.feishu_default_user_id:
            receive_id = settings.feishu_default_user_id
            receive_id_type = "open_id"
        elif settings.feishu_default_chat_id:
            receive_id = settings.feishu_default_chat_id
            receive_id_type = "chat_id"
        else:
            logger.warning("feishu_no_recipient_configured")
            return False

        # Build message card.
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": content
                }
            }
        ]

        # Add link button.
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
            logger.info(
                "feishu_notification_sent",
                title_hash=hash_identifier(title),
                receive_id_hash=hash_identifier(receive_id),
            )
            return True

        except Exception as e:
            logger.error("feishu_notification_failed", error=str(e))
            return False

    async def _send_email(self, title: str, content: str, **kwargs) -> bool:
        """Send email. Not implemented."""
        logger.warning("email_notification_not_implemented")
        return False

    async def _send_sms(self, content: str, **kwargs) -> bool:
        """Send SMS. Not implemented."""
        logger.warning("sms_notification_not_implemented")
        return False


# Global notification service instance.
notification_service = NotificationService()
