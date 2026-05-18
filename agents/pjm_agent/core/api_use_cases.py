"""Application use cases for PJM HTTP operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class PMApiAgentPort(Protocol):
    """Agent operations required by the PJM HTTP application use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""

    async def approve_decomposition(
        self,
        wp_id: int,
        approved_by: str,
    ) -> dict[str, Any] | None:
        """Approve a pending decomposition."""

    async def reject_decomposition(
        self,
        wp_id: int,
        *,
        rejected_by: str,
        reason: str,
    ) -> dict[str, Any] | None:
        """Reject a pending decomposition."""


class PMApiConfigFailedError(Exception):
    """Raised when reading PM configuration fails."""


class PMApiConfigRefreshFailedError(Exception):
    """Raised when refreshing PM configuration fails."""


class PMApiAlertsFailedError(Exception):
    """Raised when reading PM alerts fails."""


class PMApiReportFailedError(Exception):
    """Raised when a PM report action returns an error result."""


class PMApiDecompositionRetryFailedError(Exception):
    """Raised when retrying decomposition fails."""


class PMApiDecompositionNotFoundError(Exception):
    """Raised when a decomposition record cannot be found."""


class PMApiDecompositionUnavailableError(Exception):
    """Raised when decomposition approval state is unavailable."""


class PMApiDecompositionForbiddenError(Exception):
    """Raised when a decomposition action is forbidden."""


@dataclass(frozen=True, slots=True)
class PMDecompositionActionCommand:
    """Command for approving or rejecting a decomposition."""

    wp_id: int
    operator: str
    reason: str = ""


class PMApiUseCase:
    """Application boundary used by PJM HTTP routes."""

    def __init__(self, agent: PMApiAgentPort):
        self._agent = agent

    async def get_config(self) -> dict[str, Any]:
        try:
            return await self._agent.handle_request({"action": "config"})
        except Exception as exc:
            raise PMApiConfigFailedError(str(exc)) from exc

    async def refresh_config(self) -> dict[str, Any]:
        try:
            return await self._agent.handle_request({"action": "refresh_config"})
        except Exception as exc:
            raise PMApiConfigRefreshFailedError(str(exc)) from exc

    async def get_alerts(self) -> dict[str, Any]:
        try:
            result = await self._agent.handle_request({"action": "alerts"})
        except Exception as exc:
            raise PMApiAlertsFailedError(str(exc)) from exc
        alerts = result.get("alerts", [])
        return {"total": len(alerts), "alerts": alerts}

    async def trigger_daily_report(self) -> dict[str, Any]:
        return await self._run_report_action({"action": "daily_report"})

    async def trigger_weekly_report(self) -> dict[str, Any]:
        return await self._run_report_action({"action": "weekly_report"})

    async def retry_decomposition(self, wp_id: int) -> dict[str, Any]:
        result = await self._agent.handle_request(
            {"action": "retry_decompose", "wp_id": wp_id}
        )
        if result.get("error"):
            raise PMApiDecompositionRetryFailedError(str(result.get("error", "")))
        return result

    async def get_decomposition(self, wp_id: int) -> dict[str, Any]:
        result = await self._agent.handle_request(
            {"action": "get_decompose", "wp_id": wp_id}
        )
        if not result:
            raise PMApiDecompositionNotFoundError(str(wp_id))
        return result

    async def approve_decomposition(
        self,
        command: PMDecompositionActionCommand,
    ) -> dict[str, Any]:
        result = await self._agent.approve_decomposition(
            command.wp_id,
            approved_by=command.operator,
        )
        if result is None:
            raise PMApiDecompositionUnavailableError(str(command.wp_id))
        if result.get("error"):
            raise PMApiDecompositionForbiddenError(str(result["error"]))
        return {
            "success": True,
            "wp_id": command.wp_id,
            "action": "approve",
            "message": (
                f"Written to OP: {result.get('story_count', 0)} US, "
                f"{result.get('task_count', 0)} Task"
            ),
            "subject": result.get("subject", ""),
            "story_count": result.get("story_count", 0),
            "task_count": result.get("task_count", 0),
        }

    async def reject_decomposition(
        self,
        command: PMDecompositionActionCommand,
    ) -> dict[str, Any]:
        result = await self._agent.reject_decomposition(
            command.wp_id,
            rejected_by=command.operator,
            reason=command.reason,
        )
        if result is None:
            raise PMApiDecompositionUnavailableError(str(command.wp_id))
        if result.get("error"):
            raise PMApiDecompositionForbiddenError(str(result["error"]))
        return {
            "success": True,
            "wp_id": command.wp_id,
            "action": "reject",
            "message": "Rejected",
            "subject": result.get("subject", ""),
        }

    async def _run_report_action(self, request: dict[str, Any]) -> dict[str, Any]:
        result = await self._agent.handle_request(request)
        if result.get("error"):
            raise PMApiReportFailedError(str(result.get("error", "")))
        return result
