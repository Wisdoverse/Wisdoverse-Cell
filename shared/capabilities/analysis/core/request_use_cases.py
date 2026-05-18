"""Application use cases for Analysis agent requests."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core import unknown_action_error


class AnalysisReportGeneratorPort(Protocol):
    """Report generation operation required by Analysis request handling."""

    async def generate(self) -> dict[str, Any]:
        """Generate an analysis report."""


class AnalysisMilestoneCheckerPort(Protocol):
    """Milestone risk operation required by Analysis request handling."""

    async def check(self) -> list[dict[str, Any]]:
        """Check milestone risks."""


class AnalysisRequestUseCase:
    """Dispatch and execute Analysis agent request actions."""

    def __init__(
        self,
        *,
        daily: AnalysisReportGeneratorPort | None,
        weekly: AnalysisReportGeneratorPort | None,
        milestone: AnalysisMilestoneCheckerPort | None,
    ):
        self._daily = daily
        self._weekly = weekly
        self._milestone = milestone

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "daily_report":
            return await self._require_daily().generate()
        if action == "weekly_report":
            return await self._require_weekly().generate()
        if action == "check_milestones":
            risks = await self._require_milestone().check()
            return {"risks": risks}
        return unknown_action_error()

    def _require_daily(self) -> AnalysisReportGeneratorPort:
        if self._daily is None:
            raise RuntimeError("daily_report_generator_not_initialized")
        return self._daily

    def _require_weekly(self) -> AnalysisReportGeneratorPort:
        if self._weekly is None:
            raise RuntimeError("weekly_report_generator_not_initialized")
        return self._weekly

    def _require_milestone(self) -> AnalysisMilestoneCheckerPort:
        if self._milestone is None:
            raise RuntimeError("milestone_checker_not_initialized")
        return self._milestone
