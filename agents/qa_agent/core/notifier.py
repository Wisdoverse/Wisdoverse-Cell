"""QA notification fan-out: EventBus + Feishu + GitLab MR.

Each channel is fault-isolated — failure in one does not block others.
Results are collected into a notification_summary dict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shared.config import settings
from shared.core import FeishuWebhookPort, GitLabMergeRequestNotePort
from shared.infra.event_bus import EventBus, event_bus
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from .card_ports import QualityCardRendererPort

logger = get_logger("qa_agent.notifier")


class QANotifier:
    """Orchestrates notifications across all channels."""

    def __init__(
        self,
        bus: EventBus | None = None,
        gitlab: GitLabMergeRequestNotePort | None = None,
        feishu_webhook: FeishuWebhookPort | None = None,
        card_renderer: QualityCardRendererPort | None = None,
    ):
        self._bus = bus or event_bus
        self._gitlab = gitlab
        self._feishu_webhook = feishu_webhook
        self._card_renderer = card_renderer

    async def notify_all(
        self,
        *,
        run_id: str,
        agent_name: str,
        summary: dict,
        findings: list[dict],
        duration_seconds: float,
        commit_sha: str | None = None,
        mr_iid: int | None = None,
        gitlab_project_id: int | None = None,
        trigger: str = "event",
        level: str = "all",
        target: str = "",
        report_markdown: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Fan-out notifications to all channels.

        Returns:
            notification_summary with success/failure per channel.
        """
        result: dict[str, Any] = {}

        # 1. EventBus — always publish qa.acceptance-completed
        result["eventbus"] = await self._publish_events(
            run_id=run_id,
            agent_name=agent_name,
            summary=summary,
            findings=findings,
            duration_seconds=duration_seconds,
            commit_sha=commit_sha,
            mr_iid=mr_iid,
            gitlab_project_id=gitlab_project_id,
            trigger=trigger,
            level=level,
            target=target,
            report_markdown=report_markdown,
            trace_id=trace_id,
        )

        # 2. Feishu — only on L0 FAIL or high-severity L1
        should_feishu = self._should_notify_feishu(summary, findings)
        if should_feishu:
            result["feishu"] = await self._send_feishu(
                agent_name=agent_name,
                summary=summary,
                findings=findings,
                mr_iid=mr_iid,
            )
        else:
            result["feishu"] = {"sent": False, "reason": "below_threshold"}

        # 3. GitLab MR comment — only if mr_iid present
        if mr_iid and report_markdown:
            result["gitlab"] = await self._post_gitlab_comment(
                mr_iid=mr_iid,
                report_markdown=report_markdown,
                project_id=str(gitlab_project_id) if gitlab_project_id else None,
            )
        else:
            result["gitlab"] = {"sent": False, "reason": "no_mr"}

        return result

    async def _publish_events(self, **kwargs) -> dict:
        """Publish qa.acceptance-completed (always) and qa.gate-failed (on L0 fail)."""
        try:
            summary = kwargs["summary"]

            # Always publish completion
            completed_payload = {
                "run_id": kwargs["run_id"],
                "agent_name": kwargs["agent_name"],
                "commit_sha": kwargs.get("commit_sha"),
                "mr_iid": kwargs.get("mr_iid"),
                "gitlab_project_id": kwargs.get("gitlab_project_id"),
                "trigger": kwargs["trigger"],
                "level": kwargs["level"],
                "target": kwargs["target"],
                "summary": summary,
                "findings": kwargs["findings"],
                "duration_seconds": kwargs["duration_seconds"],
                "report_markdown": kwargs.get("report_markdown"),
                "completed_at": datetime.now(UTC).isoformat(),
            }
            await self._bus.publish(
                Event.create(
                    event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
                    source_agent="qa-agent",
                    payload=completed_payload,
                    trace_id=kwargs.get("trace_id"),
                )
            )

            # Publish gate-failed if L0 failed
            if summary.get("l0_gate") == "FAIL":
                blocking = [
                    f
                    for f in kwargs["findings"]
                    if f.get("level") == "L0" and f.get("status") == "FAIL"
                ]
                await self._bus.publish(
                    Event.create(
                        event_type=EventTypes.QA_GATE_FAILED,
                        source_agent="qa-agent",
                        payload={
                            "run_id": kwargs["run_id"],
                            "agent_name": kwargs["agent_name"],
                            "commit_sha": kwargs.get("commit_sha"),
                            "mr_iid": kwargs.get("mr_iid"),
                            "gitlab_project_id": kwargs.get("gitlab_project_id"),
                            "l0_failure_count": summary.get("l0_failures", 0),
                            "blocking_findings": blocking[:10],
                            "duration_seconds": kwargs["duration_seconds"],
                            "report_markdown": kwargs.get("report_markdown"),
                        },
                        trace_id=kwargs.get("trace_id"),
                    )
                )

            return {"sent": True}
        except Exception as e:
            logger.error("eventbus_publish_failed", error=str(e))
            return {"sent": False, "error": str(e)}

    def _should_notify_feishu(
        self,
        summary: dict,
        findings: list[dict],
    ) -> bool:
        """Determine if Feishu notification is warranted."""
        # Always notify on L0 FAIL
        if summary.get("l0_gate") == "FAIL":
            return True

        # Notify on configured high-severity L1 checks
        high_checks = set(settings.qa_high_severity_check_list)
        if high_checks:
            for f in findings:
                if (
                    f.get("level") == "L1"
                    and f.get("status") == "WARN"
                    and f.get("check") in high_checks
                ):
                    return True

        return False

    async def _send_feishu(
        self,
        agent_name: str,
        summary: dict,
        findings: list[dict],
        mr_iid: int | None = None,
    ) -> dict:
        """Send Feishu card notification."""
        webhook = settings.qa_feishu_webhook_url or settings.feishu_webhook_url or ""
        if not webhook:
            return {"sent": False, "reason": "no_webhook"}
        if not self._feishu_webhook:
            return {"sent": False, "reason": "no_webhook_adapter"}
        if not self._card_renderer:
            return {"sent": False, "reason": "no_card_renderer"}

        card = self._card_renderer.build_acceptance_alert_message(
            agent_name=agent_name,
            summary=summary,
            findings=findings,
            mr_iid=mr_iid,
            gitlab_api_url=settings.gitlab_api_url,
            gitlab_project_id=settings.gitlab_project_id,
        )

        try:
            ok = await self._feishu_webhook.send_interactive_card(
                webhook_url=webhook,
                card=card,
            )
            if not ok:
                return {"sent": False, "reason": "feishu_webhook_rejected"}
            logger.info("feishu_sent", agent_name=agent_name)
            return {"sent": True}
        except Exception as e:
            logger.error("feishu_failed", error=str(e))
            return {"sent": False, "error": str(e)}

    async def _post_gitlab_comment(
        self,
        mr_iid: int,
        report_markdown: str,
        project_id: str | None = None,
    ) -> dict:
        """Post acceptance report as GitLab MR comment."""
        if not self._gitlab:
            return {"sent": False, "reason": "gitlab_adapter_not_configured"}
        try:
            ok = await self._gitlab.upsert_mr_note(
                mr_iid,
                report_markdown,
                project_id=project_id,
            )
            if ok:
                return {"sent": True}
            return {"sent": False, "reason": "gitlab_api_rejected"}
        except Exception as e:
            logger.error("gitlab_comment_failed", mr_iid=mr_iid, error=str(e))
            return {"sent": False, "error": str(e)}
