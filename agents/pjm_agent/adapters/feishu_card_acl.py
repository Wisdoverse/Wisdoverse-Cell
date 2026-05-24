"""PJM-local anti-corruption adapter for Feishu card rendering."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from shared.core.identifiers import WorkPackageId
from shared.integrations.feishu.cards.pjm import FeishuPJMCardRenderer

from ..core.card_ports import PJMCardRendererPort


class SharedFeishuPJMCardRendererPort(Protocol):
    """Shared Feishu renderer contract consumed by the PJM ACL adapter."""

    def build_daily_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Build a daily report card in Feishu schema."""

    def build_weekly_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Build a weekly report card in Feishu schema."""

    def build_decomposition_approval_card(
        self,
        wp_id: int,
        subject: str,
        wbs_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a decomposition approval card in Feishu schema."""

    def build_task_refinement_approval_card(
        self,
        wp_id: int,
        subject: str,
        reason: str,
        subtasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a task-refinement approval card in Feishu schema."""


@dataclass(frozen=True, slots=True)
class FeishuDecompositionApprovalCard:
    """PJM decomposition approval data translated for Feishu card rendering."""

    wp_id: WorkPackageId
    subject: str
    wbs_result: Mapping[str, Any]

    @classmethod
    def from_decomposition(
        cls,
        *,
        wp_id: WorkPackageId,
        subject: str,
        wbs_result: Mapping[str, Any],
    ) -> "FeishuDecompositionApprovalCard":
        summary = str(wbs_result.get("summary") or "").strip()
        display_subject = (subject or summary or f"WP#{wp_id}").strip()
        return cls(
            wp_id=wp_id,
            subject=display_subject,
            wbs_result=deepcopy(dict(wbs_result)),
        )

    def shared_renderer_kwargs(self) -> dict[str, Any]:
        """Return primitive values expected by the shared Feishu renderer."""
        return {
            "wp_id": int(self.wp_id),
            "subject": self.subject,
            "wbs_result": deepcopy(dict(self.wbs_result)),
        }


@dataclass(frozen=True, slots=True)
class FeishuTaskRefinementApprovalCard:
    """PJM task-refinement approval data translated for Feishu card rendering."""

    wp_id: WorkPackageId
    subject: str
    reason: str
    subtasks: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_task_refinement(
        cls,
        *,
        wp_id: WorkPackageId,
        subject: str,
        reason: str,
        subtasks: list[dict[str, Any]],
    ) -> "FeishuTaskRefinementApprovalCard":
        display_subject = (subject or f"WP#{wp_id}").strip()
        return cls(
            wp_id=wp_id,
            subject=display_subject,
            reason=reason,
            subtasks=tuple(deepcopy(task) for task in subtasks),
        )

    def shared_renderer_kwargs(self) -> dict[str, Any]:
        """Return primitive values expected by the shared Feishu renderer."""
        return {
            "wp_id": int(self.wp_id),
            "subject": self.subject,
            "reason": self.reason,
            "subtasks": [deepcopy(dict(task)) for task in self.subtasks],
        }


class PJMFeishuCardACL(PJMCardRendererPort):
    """Translate PJM decomposition data before calling shared Feishu renderers."""

    def __init__(
        self,
        renderer: SharedFeishuPJMCardRendererPort | None = None,
    ) -> None:
        self._renderer = renderer or FeishuPJMCardRenderer()

    def build_daily_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        return self._renderer.build_daily_report_card(stats)

    def build_weekly_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        return self._renderer.build_weekly_report_card(stats)

    def build_decomposition_approval_card(
        self,
        wp_id: WorkPackageId,
        subject: str,
        wbs_result: dict[str, Any],
    ) -> dict[str, Any]:
        card = FeishuDecompositionApprovalCard.from_decomposition(
            wp_id=wp_id,
            subject=subject,
            wbs_result=wbs_result,
        )
        return self._renderer.build_decomposition_approval_card(**card.shared_renderer_kwargs())

    def build_task_refinement_approval_card(
        self,
        wp_id: WorkPackageId,
        subject: str,
        reason: str,
        subtasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        card = FeishuTaskRefinementApprovalCard.from_task_refinement(
            wp_id=wp_id,
            subject=subject,
            reason=reason,
            subtasks=subtasks,
        )
        return self._renderer.build_task_refinement_approval_card(**card.shared_renderer_kwargs())


__all__ = [
    "FeishuDecompositionApprovalCard",
    "FeishuTaskRefinementApprovalCard",
    "PJMFeishuCardACL",
]
