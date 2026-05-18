"""Application use cases for PJM agent requests."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core import request_error, unknown_action_error
from shared.utils.logger import get_logger

from .decomposition_ports import PJMDecompositionStore

logger = get_logger("pjm_agent.requests")
STALE_APPROVAL_HOURS = 24


class PJMConfigPort(Protocol):
    """Configuration operations required by PJM request handling."""

    members: list[Any]
    projects: list[Any]
    rules: dict[str, Any]

    async def refresh(self) -> None:
        """Refresh PM configuration from its source."""


class PJMAlertPort(Protocol):
    """Alert operations required by PJM request handling."""

    async def check_all(self) -> list[dict[str, Any]]:
        """Return active PM alerts."""


class PJMPushPort(Protocol):
    """Push operations required by PJM request handling."""

    async def push_alerts(self, alerts: list[dict[str, Any]]) -> Any:
        """Push active alerts."""

    async def send_stale_approval_reminder(self, *, wp_id: int, subject: str) -> Any:
        """Send a stale approval reminder."""


class PJMReportPort(Protocol):
    """Report operations required by PJM request handling."""

    async def generate_daily(self) -> dict[str, Any]:
        """Generate a daily report."""

    async def generate_weekly(self) -> dict[str, Any]:
        """Generate a weekly report."""

    async def push_card(self, card: dict[str, Any]) -> Any:
        """Push one report card."""


class PJMDecompositionRequestPort(Protocol):
    """Decomposition read/retry operations required by PJM request handling."""

    async def retry_decompose(self, wp_id: int | None) -> dict[str, Any]:
        """Retry decomposition for one work package."""

    async def get_decompose(self, wp_id: int | None) -> dict[str, Any]:
        """Return one decomposition record."""


class PJMRequestUseCase:
    """Dispatch and execute PJM agent request actions."""

    def __init__(
        self,
        *,
        config: PJMConfigPort,
        alert: PJMAlertPort,
        push: PJMPushPort,
        report: PJMReportPort,
        decomposition: PJMDecompositionRequestPort,
        decomposition_store: PJMDecompositionStore,
    ):
        self._config = config
        self._alert = alert
        self._push = push
        self._report = report
        self._decomposition = decomposition
        self._decomposition_store = decomposition_store

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "config":
            return {
                "members": self._config.members,
                "projects": self._config.projects,
                "rules": self._config.rules,
            }
        if action == "alerts":
            alerts = await self._alert.check_all()
            return {"alerts": alerts}
        if action == "refresh_config":
            await self._config.refresh()
            return {"status": "refreshed"}
        if action == "push_alerts":
            alerts = request.get("alerts", [])
            await self._push.push_alerts(alerts)
            return {"status": "pushed", "count": len(alerts)}
        if action == "retry_decompose":
            return await self._decomposition.retry_decompose(request.get("wp_id"))
        if action == "get_decompose":
            return await self._decomposition.get_decompose(request.get("wp_id"))
        if action == "daily_report":
            return await self._run_report("daily")
        if action == "weekly_report":
            return await self._run_report("weekly")
        if action == "check_stale_approvals":
            await self._check_stale_approvals()
            return {"status": "ok"}
        return unknown_action_error()

    async def _run_report(self, report_type: str) -> dict[str, Any]:
        try:
            if report_type == "weekly":
                result = await self._report.generate_weekly()
            else:
                result = await self._report.generate_daily()
            await self._report.push_card(result["card"])
            return {"status": "sent", "total": result["stats"]["total"]}
        except Exception as exc:
            logger.error("report_failed", report_type=report_type, error=str(exc))
            return request_error("report_failed", "report_failed")

    async def _check_stale_approvals(self) -> None:
        try:
            stale = await self._decomposition_store.list_stale_pending(
                older_than_hours=STALE_APPROVAL_HOURS
            )
            if not stale:
                return
            logger.info("stale_approvals_found", count=len(stale))
            for record in stale:
                subject = (record.decompose_result or {}).get(
                    "summary",
                    f"WP#{record.wp_id}",
                )
                try:
                    await self._push.send_stale_approval_reminder(
                        wp_id=record.wp_id,
                        subject=subject,
                    )
                except Exception as exc:
                    logger.warning(
                        "stale_approval_reminder_failed",
                        wp_id=record.wp_id,
                        error=str(exc),
                    )
        except Exception as exc:
            logger.error("stale_approvals_check_failed", error=str(exc))
