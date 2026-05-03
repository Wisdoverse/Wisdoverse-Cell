"""Pure configuration values for the user interaction gateway core."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserInteractionCoreConfig:
    """Settings the gateway core can consume without importing global config."""

    chat_model: str = "claude-sonnet-4-20250514"
    summary_model: str = "claude-haiku-4-5-20251001"

    @classmethod
    def from_values(
        cls,
        *,
        chat_model: str | None = "claude-sonnet-4-20250514",
        summary_model: str | None = "claude-haiku-4-5-20251001",
    ) -> "UserInteractionCoreConfig":
        return cls(
            chat_model=chat_model or "claude-sonnet-4-20250514",
            summary_model=summary_model or "claude-haiku-4-5-20251001",
        )
