"""Feishu card renderer adapter for QA workflows."""

from __future__ import annotations

from typing import Any


class FeishuQualityCardRenderer:
    """Render QA notification payloads using Feishu's interactive-card schema."""

    def build_acceptance_alert_message(
        self,
        *,
        agent_name: str,
        summary: dict[str, Any],
        findings: list[dict[str, Any]],
        mr_iid: int | None = None,
        gitlab_api_url: str = "",
        gitlab_project_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Build a Feishu webhook message body for acceptance alerts."""
        l0 = summary.get("l0_gate", "?")
        l1 = summary.get("l1_check", "?")
        status_emoji = "\u274c" if l0 == "FAIL" else "\u26a0\ufe0f"

        failure_lines = []
        for finding in findings[:5]:
            if finding.get("status") not in ("FAIL", "WARN"):
                continue
            loc = finding.get("file", "")
            if finding.get("line"):
                loc += f":{finding['line']}"
            failure_lines.append(
                f"- [{finding.get('level')}] **{finding.get('check')}**: "
                f"{(finding.get('details') or '')[:60]} `{loc}`"
            )

        mr_link = self._build_mr_link(
            mr_iid=mr_iid,
            gitlab_api_url=gitlab_api_url,
            gitlab_project_id=gitlab_project_id,
        )

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{status_emoji} QA: {agent_name} L0={l0} L1={l1}",
                    },
                    "template": "red" if l0 == "FAIL" else "orange",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": (
                            f"**Agent**: {agent_name}\n"
                            f"**L0**: {l0} | **L1**: {l1}\n\n"
                            + ("\n".join(failure_lines) or "No issues")
                            + mr_link
                        ),
                    },
                ],
            },
        }

    def _build_mr_link(
        self,
        *,
        mr_iid: int | None,
        gitlab_api_url: str,
        gitlab_project_id: str | int | None,
    ) -> str:
        if not mr_iid or not gitlab_api_url or not gitlab_project_id:
            return ""

        gitlab_url = gitlab_api_url.replace("/api/v4", "")
        return (
            f"\n[MR !{mr_iid}]"
            f"({gitlab_url}/{gitlab_project_id}/-/merge_requests/{mr_iid})"
        )
