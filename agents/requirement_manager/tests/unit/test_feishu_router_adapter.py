"""Unit tests for Requirement-local Feishu router adapter."""

from __future__ import annotations

from importlib import import_module
from unittest.mock import Mock

from agents.requirement_manager.integrations.feishu import router
from agents.requirement_manager.integrations.feishu.router import (
    register_requirement_feishu_handlers,
)


def test_requirement_feishu_router_adapter_exposes_shared_router() -> None:
    assert router.prefix == "/api/feishu"


def test_register_requirement_feishu_handlers_translates_to_shared_router(monkeypatch) -> None:
    router_adapter = import_module("agents.requirement_manager.integrations.feishu.router")
    register_shared_handlers = Mock()
    monkeypatch.setattr(router_adapter, "_register_shared_handlers", register_shared_handlers)
    event_handler = object()
    bot_handler = object()
    card_handler = object()
    message_recorder = object()

    register_requirement_feishu_handlers(
        event_handler=event_handler,
        bot_handler=bot_handler,
        card_handler=card_handler,
        message_recorder=message_recorder,
    )

    register_shared_handlers.assert_called_once_with(
        event_h=event_handler,
        bot_h=bot_handler,
        card_h=card_handler,
        message_h=message_recorder,
    )
