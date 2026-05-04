"""Pure configuration values for the development agent core."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DevCoreConfig:
    """Settings the dev core can consume without importing global config."""

    decompose_model: str = "claude-opus-4-20250514"
    gitlab_project_id: int = 0

    @classmethod
    def from_values(
        cls,
        *,
        decompose_model: str | None = "claude-opus-4-20250514",
        gitlab_project_id: int | None = 0,
    ) -> "DevCoreConfig":
        return cls(
            decompose_model=decompose_model or "claude-sonnet-4-20250514",
            gitlab_project_id=gitlab_project_id or 0,
        )
