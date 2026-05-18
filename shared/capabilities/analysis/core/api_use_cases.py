"""Application use cases for Analysis HTTP operations."""
from __future__ import annotations

from typing import Any, Protocol


class AnalysisApiAgentPort(Protocol):
    """Agent operations required by the Analysis HTTP application use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


class AnalysisApiDailyReportFailedError(Exception):
    """Raised when daily report generation fails."""


class AnalysisApiWeeklyReportFailedError(Exception):
    """Raised when weekly report generation fails."""


class AnalysisApiRiskCheckFailedError(Exception):
    """Raised when risk checking fails."""


class AnalysisApiUseCase:
    """Application boundary used by Analysis HTTP routes."""

    def __init__(self, agent: AnalysisApiAgentPort):
        self._agent = agent

    async def generate_daily_report(self) -> dict[str, Any]:
        try:
            return await self._agent.handle_request({"action": "daily_report"})
        except Exception as exc:
            raise AnalysisApiDailyReportFailedError(str(exc)) from exc

    async def generate_weekly_report(self) -> dict[str, Any]:
        try:
            return await self._agent.handle_request({"action": "weekly_report"})
        except Exception as exc:
            raise AnalysisApiWeeklyReportFailedError(str(exc)) from exc

    async def check_risks(self) -> dict[str, Any]:
        try:
            result = await self._agent.handle_request({"action": "check_milestones"})
        except Exception as exc:
            raise AnalysisApiRiskCheckFailedError(str(exc)) from exc
        risks = result.get("risks", [])
        return {"total": len(risks), "risks": risks}
