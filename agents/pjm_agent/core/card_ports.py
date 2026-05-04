"""Card-rendering ports used by PJM application services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PJMCardRendererPort(Protocol):
    """Build platform-specific PJM cards behind an injected adapter boundary."""

    def build_daily_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Build a daily report card from aggregated report stats."""

    def build_weekly_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Build a weekly report card from aggregated report stats."""

    def build_decomposition_approval_card(
        self,
        wp_id: int,
        subject: str,
        wbs_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a decomposition approval card."""

    def build_task_refinement_approval_card(
        self,
        wp_id: int,
        subject: str,
        reason: str,
        subtasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a task-refinement approval card."""
