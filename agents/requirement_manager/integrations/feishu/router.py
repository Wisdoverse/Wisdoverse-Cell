"""Requirement-local adapter for the shared Feishu webhook router."""

from __future__ import annotations

from typing import Any

from shared.integrations.feishu.router import (
    init_handlers as _register_shared_handlers,
)
from shared.integrations.feishu.router import (
    router,
)


def register_requirement_feishu_handlers(
    *,
    event_handler: Any | None = None,
    bot_handler: Any | None = None,
    card_handler: Any | None = None,
    message_recorder: Any | None = None,
) -> None:
    """Register Requirement-owned handlers behind the shared webhook router."""
    _register_shared_handlers(
        event_h=event_handler,
        bot_h=bot_handler,
        card_h=card_handler,
        message_h=message_recorder,
    )


__all__ = ["register_requirement_feishu_handlers", "router"]
