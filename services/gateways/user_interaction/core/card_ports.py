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
