"""Card-rendering ports for user-interaction tools."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolCardRendererPort(Protocol):
    """Build platform-specific confirmation cards behind an adapter boundary."""

    def build_bitable_update_confirmation(
        self,
        *,
        title: str,
        record_id: str,
        field_lines: str,
        action_id: str,
        is_group_chat: bool,
    ) -> dict[str, Any]:
        """Build a confirmation card for a proposed Bitable record update."""

    def build_bitable_create_confirmation(
        self,
        *,
        field_lines: str,
        action_id: str,
        is_group_chat: bool,
    ) -> dict[str, Any]:
        """Build a confirmation card for a proposed Bitable record creation."""

    def build_bitable_operation_expired(self, *, operation: str) -> dict[str, Any]:
        """Build an expiration card for a pending Bitable operation."""

    def build_bitable_update_success(
        self,
        *,
        record_id: str,
        field_lines: str,
    ) -> dict[str, Any]:
        """Build a success card for a confirmed Bitable update."""

    def build_bitable_update_failure(self, *, record_id: str) -> dict[str, Any]:
        """Build a failure card for a Bitable update."""

    def build_bitable_create_success(
        self,
        *,
        record_id: str,
        field_lines: str,
    ) -> dict[str, Any]:
        """Build a success card for a confirmed Bitable create."""

    def build_bitable_create_failure(self) -> dict[str, Any]:
        """Build a failure card for a Bitable create."""

    def build_bitable_rejection(self, *, action_type: str) -> dict[str, Any]:
        """Build a cancellation card for a rejected Bitable operation."""

    def build_ai_reply_card(self, *, reply: str, elapsed: float) -> dict[str, Any]:
        """Build an AI reply card for Feishu webhook responses."""


_tool_card_renderer: ToolCardRendererPort | None = None


def configure_tool_card_renderer(renderer: ToolCardRendererPort | None) -> None:
    """Configure the card renderer used by user-interaction HTTP routes."""
    global _tool_card_renderer
    _tool_card_renderer = renderer


def require_tool_card_renderer() -> ToolCardRendererPort:
    """Return the configured card renderer or fail closed."""
    if _tool_card_renderer is None:
        raise RuntimeError("tool card renderer is not configured")
    return _tool_card_renderer
