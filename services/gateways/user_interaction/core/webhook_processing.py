"""Application use cases for Feishu webhook message processing."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class WebhookAgentPort(Protocol):
    """Agent request operations required by webhook message processing."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a normalized user-interaction request."""


class WebhookMessengerPort(Protocol):
    """Feishu message operations required by webhook message processing."""

    async def add_reaction(self, message_id: str, emoji_type: str = "OnIt") -> bool:
        """Add a reaction to the inbound message."""

    async def send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: str,
    ) -> str:
        """Send a new message."""

    async def reply_message(self, message_id: str, msg_type: str, content: str) -> str:
        """Reply to an existing message."""


ReplyCardBuilder = Callable[[str, float], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class WebhookProcessCommand:
    """Command for processing one normalized Feishu message."""

    user_id: str
    text: str
    message: dict[str, Any]
    chat_type: str
    user_name: str = ""
    chat_id: str = ""


@dataclass(frozen=True, slots=True)
class WebhookProcessResult:
    """Outcome reported to the HTTP adapter for logging and metrics."""

    status: str
    elapsed: float
    error: str = ""
    reply_error: str = ""


class WebhookMessageProcessingUseCase:
    """Application boundary for user assistant webhook message processing."""

    async def process_message(
        self,
        command: WebhookProcessCommand,
        *,
        agent: WebhookAgentPort,
        messenger: WebhookMessengerPort,
        build_reply_card: ReplyCardBuilder,
    ) -> WebhookProcessResult:
        msg_id = command.message.get("message_id", "")

        try:
            await messenger.add_reaction(msg_id, "OnIt")
        except Exception:
            pass

        start = time.time()
        try:
            result = await agent.handle_request(
                {
                    "action": "chat_user_assistant",
                    "message": command.text,
                    "user_id": command.user_id,
                    "user_name": command.user_name,
                    "chat_id": command.chat_id,
                    "chat_type": command.chat_type,
                }
            )
            reply = result.get("reply", "")
            elapsed = time.time() - start
            if not reply:
                return WebhookProcessResult(status="card_sent", elapsed=elapsed)

            card = build_reply_card(reply, elapsed)
            card_content = json.dumps(card, ensure_ascii=False)
            if command.chat_type == "p2p":
                await messenger.send_message(
                    receive_id=command.user_id,
                    receive_id_type="open_id",
                    msg_type="interactive",
                    content=card_content,
                )
            elif msg_id:
                await messenger.reply_message(
                    message_id=msg_id,
                    msg_type="interactive",
                    content=card_content,
                )
            return WebhookProcessResult(status="replied", elapsed=elapsed)
        except Exception as exc:
            elapsed = time.time() - start
            reply_error = await self._send_error_reply(
                command,
                msg_id=msg_id,
                messenger=messenger,
            )
            return WebhookProcessResult(
                status="error",
                elapsed=elapsed,
                error=str(exc),
                reply_error=reply_error,
            )

    async def _send_error_reply(
        self,
        command: WebhookProcessCommand,
        *,
        msg_id: str,
        messenger: WebhookMessengerPort,
    ) -> str:
        try:
            error_content = json.dumps(
                {"text": "抱歉，处理消息时出现问题，请稍后再试。"},
                ensure_ascii=False,
            )
            if command.chat_type == "p2p":
                await messenger.send_message(
                    receive_id=command.user_id,
                    receive_id_type="open_id",
                    msg_type="text",
                    content=error_content,
                )
            elif msg_id:
                await messenger.reply_message(
                    message_id=msg_id,
                    msg_type="text",
                    content=error_content,
                )
            return ""
        except Exception as reply_err:
            return str(reply_err)
