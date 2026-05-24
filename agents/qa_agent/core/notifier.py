"""QA notification fan-out: outbox summary + Feishu + GitLab MR.

Each channel is fault-isolated — failure in one does not block others.
Results are collected into a notification_summary dict.
"""

from __future__ import annotations

from typing import Any

from shared.core import FeishuWebhookPort, GitLabMergeRequestNotePort
from shared.utils.logger import get_logger

from .card_ports import QualityCardRendererPort
from .config import QACoreConfig
from .domain.acceptance_verdict import AcceptanceVerdict
from .domain.acceptance_vocabulary import (
    is_warning_finding,
)

logger = get_logger("qa_agent.notifier")


class QANotifier:
    """Orchestrates notifications across all channels."""

    def __init__(
        self,
        gitlab: GitLabMergeRequestNotePort | None = None,
        feishu_webhook: FeishuWebhookPort | None = None,
        card_renderer: QualityCardRendererPort | None = None,
        config: QACoreConfig | None = None,
    ):
        self._gitlab = gitlab
        self._feishu_webhook = feishu_webhook
        self._card_renderer = card_renderer
        self._config = config or QACoreConfig()

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
        eventbus_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fan-out notifications to all channels.

        Returns:
            notification_summary with success/failure per channel.
        """
        result: dict[str, Any] = {}

        # 1. EventBus — acceptance execution must provide an outbox-backed result.
        if eventbus_summary is not None:
            result["eventbus"] = eventbus_summary
        else:
            result["eventbus"] = {
                "sent": False,
                "reason": "eventbus_summary_required",
            }

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

    def _should_notify_feishu(
        self,
        summary: dict,
        findings: list[dict],
    ) -> bool:
        """Determine if Feishu notification is warranted."""
        # Always notify on L0 FAIL
        if AcceptanceVerdict.from_summary(summary).is_blocking:
            return True

        # Notify on configured high-severity L1 checks
        high_checks = set(self._config.high_severity_check_list)
        if high_checks:
            for f in findings:
                if (
                    is_warning_finding(
                        level=f.get("level", ""),
                        status=f.get("status", ""),
                    )
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
        webhook = self._config.notification_webhook_url
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
            gitlab_api_url=self._config.gitlab_api_url,
            gitlab_project_id=self._config.gitlab_project_id,
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
