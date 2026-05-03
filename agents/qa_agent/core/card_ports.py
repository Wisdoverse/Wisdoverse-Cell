"""Card-rendering ports used by QA application services."""

from __future__ import annotations

from typing import Any, Protocol


class QualityCardRendererPort(Protocol):
    """Build platform-specific QA cards behind an injected adapter boundary."""

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
        """Build an acceptance alert webhook message body."""
