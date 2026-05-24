"""Tests for PJM-local Feishu card anti-corruption adapter."""

from __future__ import annotations

from typing import Any

from agents.pjm_agent.adapters.feishu_card_acl import (
    FeishuDecompositionApprovalCard,
    FeishuTaskRefinementApprovalCard,
    PJMFeishuCardACL,
)
from shared.core.identifiers import WorkPackageId


class _FakeSharedRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def build_daily_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("daily", {"stats": stats}))
        return {"kind": "daily"}

    def build_weekly_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("weekly", {"stats": stats}))
        return {"kind": "weekly"}

    def build_decomposition_approval_card(
        self,
        wp_id: int,
        subject: str,
        wbs_result: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "decomposition",
                {"wp_id": wp_id, "subject": subject, "wbs_result": wbs_result},
            )
        )
        return {"kind": "decomposition"}

    def build_task_refinement_approval_card(
        self,
        wp_id: int,
        subject: str,
        reason: str,
        subtasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "task_refinement",
                {
                    "wp_id": wp_id,
                    "subject": subject,
                    "reason": reason,
                    "subtasks": subtasks,
                },
            )
        )
        return {"kind": "task_refinement"}


def test_feishu_decomposition_card_acl_normalizes_subject_and_wp_id() -> None:
    source_result = {"summary": "Split feature", "subtasks": [{"subject": "Story"}]}
    card = FeishuDecompositionApprovalCard.from_decomposition(
        wp_id=WorkPackageId(123),
        subject="",
        wbs_result=source_result,
    )
    source_result["subtasks"][0]["subject"] = "Mutated"

    kwargs = card.shared_renderer_kwargs()

    assert kwargs == {
        "wp_id": 123,
        "subject": "Split feature",
        "wbs_result": {"summary": "Split feature", "subtasks": [{"subject": "Story"}]},
    }
    assert isinstance(kwargs["wp_id"], int)


def test_feishu_task_refinement_card_acl_copies_subtasks() -> None:
    source_subtasks = [{"subject": "Task", "estimated_hours": 4}]
    card = FeishuTaskRefinementApprovalCard.from_task_refinement(
        wp_id=WorkPackageId(456),
        subject="Refine task",
        reason="Too broad",
        subtasks=source_subtasks,
    )
    source_subtasks[0]["subject"] = "Mutated"

    kwargs = card.shared_renderer_kwargs()

    assert kwargs == {
        "wp_id": 456,
        "subject": "Refine task",
        "reason": "Too broad",
        "subtasks": [{"subject": "Task", "estimated_hours": 4}],
    }


def test_pjm_feishu_card_acl_calls_shared_renderer_with_primitive_payload() -> None:
    shared_renderer = _FakeSharedRenderer()
    acl = PJMFeishuCardACL(shared_renderer)

    assert acl.build_decomposition_approval_card(
        wp_id=WorkPackageId(123),
        subject="Split feature",
        wbs_result={"summary": "Split feature", "subtasks": []},
    ) == {"kind": "decomposition"}
    assert acl.build_task_refinement_approval_card(
        wp_id=WorkPackageId(123),
        subject="Refine task",
        reason="Too broad",
        subtasks=[{"subject": "Task"}],
    ) == {"kind": "task_refinement"}

    assert shared_renderer.calls == [
        (
            "decomposition",
            {
                "wp_id": 123,
                "subject": "Split feature",
                "wbs_result": {"summary": "Split feature", "subtasks": []},
            },
        ),
        (
            "task_refinement",
            {
                "wp_id": 123,
                "subject": "Refine task",
                "reason": "Too broad",
                "subtasks": [{"subject": "Task"}],
            },
        ),
    ]
