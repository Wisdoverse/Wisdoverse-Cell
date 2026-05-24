"""Approval ports for user-interaction tool mutations."""

from __future__ import annotations

from typing import Protocol


class SensitiveActionApprovalPort(Protocol):
    """Port for checking control-plane approval before sensitive actions."""

    async def ensure_approved_for_sensitive_action(
        self,
        approval_id: str | None,
    ) -> object | None:
        """Raise when the approval is missing, rejected, or still pending."""
