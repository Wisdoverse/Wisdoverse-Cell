"""Pure configuration values for the PJM agent core."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def _parse_csv(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    return tuple(item.strip() for item in items if item and item.strip())


@dataclass(frozen=True)
class PJMCoreConfig:
    """Settings PJM core services can consume without importing global config."""

    decompose_model: str = "claude-opus-4-20250514"
    feishu_report_chat_id: str = ""
    decompose_notify_open_id: str = ""
    decompose_project_ids: tuple[str, ...] = ()
    feishu_pm_app_token: str = ""
    feishu_pm_member_table_id: str = ""
    feishu_pm_project_table_id: str = ""
    feishu_pm_rules_table_id: str = ""
    feishu_pm_task_table_id: str = ""

    @classmethod
    def from_values(
        cls,
        *,
        decompose_model: str | None = "claude-opus-4-20250514",
        feishu_report_chat_id: str | None = "",
        decompose_notify_open_id: str | None = "",
        decompose_project_ids: str | Iterable[str] | None = None,
        feishu_pm_app_token: str | None = "",
        feishu_pm_member_table_id: str | None = "",
        feishu_pm_project_table_id: str | None = "",
        feishu_pm_rules_table_id: str | None = "",
        feishu_pm_task_table_id: str | None = "",
    ) -> "PJMCoreConfig":
        return cls(
            decompose_model=decompose_model or "claude-sonnet-4-20250514",
            feishu_report_chat_id=feishu_report_chat_id or "",
            decompose_notify_open_id=decompose_notify_open_id or "",
            decompose_project_ids=_parse_csv(decompose_project_ids),
            feishu_pm_app_token=feishu_pm_app_token or "",
            feishu_pm_member_table_id=feishu_pm_member_table_id or "",
            feishu_pm_project_table_id=feishu_pm_project_table_id or "",
            feishu_pm_rules_table_id=feishu_pm_rules_table_id or "",
            feishu_pm_task_table_id=feishu_pm_task_table_id or "",
        )

    @property
    def decompose_notification_chat_id(self) -> str:
        return self.decompose_notify_open_id or self.feishu_report_chat_id
