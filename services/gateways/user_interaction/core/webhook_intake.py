"""Application use cases for Feishu webhook message intake."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

DEDUP_TTL_SECONDS = 300
USER_INFO_TTL_SECONDS = 3600


class WebhookCachePort(Protocol):
    """Cache operations required by webhook intake."""

    async def set(self, key: str, value: str, **kwargs: Any) -> Any:
        """Set a cache value."""

    async def get(self, key: str) -> str | None:
        """Return a cached value."""

    async def setex(self, key: str, ttl: int, value: str) -> Any:
        """Set a cached value with expiry."""


class FeishuUserDirectoryPort(Protocol):
    """Feishu user lookup operations required by webhook intake."""

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """Return Feishu user profile data."""


@dataclass(frozen=True, slots=True)
class FeishuWebhookMessage:
    """Normalized metadata for one Feishu message event."""

    msg_id: str
    msg_type: str
    chat_type: str
    chat_id: str
    user_id: str
    raw_message: dict[str, Any]


def hash_user_id(user_id: str) -> str:
    """Return a short one-way identifier for PII-safe logs."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def user_info_cache_key(user_id: str) -> str:
    """Return the Redis cache key for a Feishu user profile."""
    return f"chat:user_info:{hashlib.sha256(user_id.encode()).hexdigest()[:16]}"


class FeishuWebhookIntakeUseCase:
    """Application boundary for Feishu webhook intake decisions."""

    async def is_duplicate(
        self,
        msg_id: str,
        cache: WebhookCachePort,
        *,
        ttl_seconds: int = DEDUP_TTL_SECONDS,
    ) -> bool:
        was_set = await cache.set(
            f"chat:dedup:{msg_id}",
            "1",
            nx=True,
            ex=ttl_seconds,
        )
        return not bool(was_set)

    def extract_message_event(
        self,
        body: dict[str, Any],
    ) -> FeishuWebhookMessage | None:
        header = body.get("header", {})
        event = body.get("event", {})
        if header.get("event_type", "") != "im.message.receive_v1":
            return None

        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})
        return FeishuWebhookMessage(
            msg_id=message.get("message_id", ""),
            msg_type=message.get("message_type", ""),
            chat_type=message.get("chat_type", ""),
            chat_id=message.get("chat_id", ""),
            user_id=sender.get("open_id", "unknown"),
            raw_message=message,
        )

    def extract_text(self, message: FeishuWebhookMessage) -> str | None:
        if message.msg_type != "text":
            return None
        try:
            content = json.loads(message.raw_message.get("content", "{}"))
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            return None

        if not text:
            return None
        if text.startswith("@"):
            parts = text.split(" ", 1)
            text = parts[1] if len(parts) > 1 else ""
        text = text.strip()
        return text or None

    async def resolve_user_name(
        self,
        user_id: str,
        *,
        cache: WebhookCachePort,
        user_directory: FeishuUserDirectoryPort,
        ttl_seconds: int = USER_INFO_TTL_SECONDS,
    ) -> str:
        try:
            cache_key = user_info_cache_key(user_id)
            cached = await cache.get(cache_key)
            if cached:
                return cached
            user_info = await user_directory.get_user_info(user_id)
            user_name = user_info.get("name", "")
            if user_name:
                await cache.setex(cache_key, ttl_seconds, user_name)
            return user_name
        except Exception:
            return ""
