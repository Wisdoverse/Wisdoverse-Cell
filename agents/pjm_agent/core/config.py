"""Pure configuration values for the PJM agent core."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PJMCoreConfig:
    """Settings PJM core services can consume without importing global config."""

    decompose_model: str = "claude-opus-4-20250514"
    feishu_report_chat_id: str = ""
    decompose_notify_open_id: str = ""

    @classmethod
    def from_values(
        cls,
        *,
        decompose_model: str | None = "claude-opus-4-20250514",
        feishu_report_chat_id: str | None = "",
        decompose_notify_open_id: str | None = "",
    ) -> "PJMCoreConfig":
        return cls(
            decompose_model=decompose_model or "claude-sonnet-4-20250514",
            feishu_report_chat_id=feishu_report_chat_id or "",
            decompose_notify_open_id=decompose_notify_open_id or "",
        )

    @property
    def decompose_notification_chat_id(self) -> str:
        return self.decompose_notify_open_id or self.feishu_report_chat_id
