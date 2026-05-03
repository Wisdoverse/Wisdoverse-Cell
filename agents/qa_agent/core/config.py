"""Pure configuration values for the QA agent core."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


def _parse_check_names(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    return tuple(item.strip() for item in items if item and item.strip())


@dataclass(frozen=True)
class QACoreConfig:
    """Settings the QA core can consume without importing global config."""

    runner_timeout_seconds: int = 120
    qa_feishu_webhook_url: str = ""
    feishu_webhook_url: str = ""
    high_severity_check_list: tuple[str, ...] = field(default_factory=tuple)
    gitlab_api_url: str = ""
    gitlab_project_id: str = ""

    @classmethod
    def from_values(
        cls,
        *,
        runner_timeout_seconds: int = 120,
        qa_feishu_webhook_url: str | None = "",
        feishu_webhook_url: str | None = "",
        high_severity_check_list: str | Iterable[str] | None = None,
        gitlab_api_url: str = "",
        gitlab_project_id: str = "",
    ) -> "QACoreConfig":
        return cls(
            runner_timeout_seconds=runner_timeout_seconds,
            qa_feishu_webhook_url=qa_feishu_webhook_url or "",
            feishu_webhook_url=feishu_webhook_url or "",
            high_severity_check_list=_parse_check_names(high_severity_check_list),
            gitlab_api_url=gitlab_api_url,
            gitlab_project_id=gitlab_project_id,
        )

    @property
    def notification_webhook_url(self) -> str:
        return self.qa_feishu_webhook_url or self.feishu_webhook_url
