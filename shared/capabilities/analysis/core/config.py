"""Configuration values consumed by the analysis core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AnalysisCoreConfig:
    """Pure configuration passed into analysis core services."""

    feishu_report_chat_id: str = ""
    feishu_pm_app_token: str = ""
    feishu_pm_task_table_id: str = ""
    decompose_project_ids: tuple[str, ...] = ()

    @classmethod
    def from_values(
        cls,
        *,
        feishu_report_chat_id: str = "",
        feishu_pm_app_token: str = "",
        feishu_pm_task_table_id: str = "",
        decompose_project_ids: str | Iterable[str | int] | None = None,
    ) -> "AnalysisCoreConfig":
        return cls(
            feishu_report_chat_id=feishu_report_chat_id,
            feishu_pm_app_token=feishu_pm_app_token,
            feishu_pm_task_table_id=feishu_pm_task_table_id,
            decompose_project_ids=_parse_project_ids(decompose_project_ids),
        )


def _parse_project_ids(value: str | Iterable[str | int] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = [str(item) for item in value]
    return tuple(part.strip() for part in parts if part.strip())
