"""Approval and write workflow for PJM decomposition records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from shared.control_plane import ApprovalGateService, ApprovalRequiredError
from shared.core import request_error
from shared.core.identifiers import OpenProjectProjectId, WorkPackageId
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from .decomposition_ports import PJMDecompositionStore, PJMDecompositionTransaction
from .domain.decomposition_values import DecompositionRejectionReason
from .domain.lifecycle.decomposition_lifecycle import (
    APPROVED,
    PENDING,
    REJECTED,
    WRITE_FAILED,
    WRITING,
    DecompositionStatus,
)

logger = get_logger("pjm_agent.decomposition_approval_workflow")


class PJMOpenProjectWriterPort(Protocol):
    async def write_wbs(
        self,
        parent_wp_id: WorkPackageId,
        project_id: OpenProjectProjectId,
        wbs_result: dict,
        assignee_id: int | None = None,
    ) -> dict:
        """Write a decomposition WBS to OpenProject."""

    async def write_task_subtasks(
        self,
        parent_wp_id: WorkPackageId,
        project_id: OpenProjectProjectId,
        subtasks: list[dict],
        assignee_id: int | None = None,
    ) -> dict:
        """Write a task refinement decomposition to OpenProject."""


class PJMDecompositionPushPort(Protocol):
    async def send_decompose_failure(
        self,
        wp_id: WorkPackageId,
        subject: str,
        error_message: str,
    ) -> bool:
        """Notify operators that an approved decomposition failed to write."""


@dataclass(frozen=True)
class StagedPJMEvent:
    """Event already staged in the local PJM transaction."""

    event: Event
    wp_id: WorkPackageId | None = None


@dataclass(frozen=True)
class DecompositionApprovalWorkflowResult:
    """Approval workflow response plus post-commit events ready for publish."""

    response: dict | None
    staged_events: tuple[StagedPJMEvent, ...] = ()


class DecompositionApprovalWorkflow:
    """Owns approval, write, and rejection state transitions for decompositions."""

    def __init__(
        self,
        *,
        decomposition_store: PJMDecompositionStore,
        approval_gate: ApprovalGateService,
        op_writer: PJMOpenProjectWriterPort,
        push_service: PJMDecompositionPushPort,
        create_event_fn: Callable[..., Event],
    ) -> None:
        self._decomposition_store = decomposition_store
        self._approval_gate = approval_gate
        self._op_writer = op_writer
        self._push = push_service
        self._create_event = create_event_fn

    async def approve_decomposition(
        self,
        wp_id: WorkPackageId,
        approved_by: str,
    ) -> DecompositionApprovalWorkflowResult:
        async with self._decomposition_store.transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            if not record or record.status != PENDING:
                return DecompositionApprovalWorkflowResult(None)
            wbs_result = record.decompose_result or {}
            approval_id = wbs_result.get("control_plane_approval_id")
            if approval_id and not approved_by:
                return DecompositionApprovalWorkflowResult(
                    request_error(
                        "approved_by required for control-plane approval",
                        "control_plane_approval_resolver_required",
                        wp_id=wp_id,
                        control_plane_approval_id=approval_id,
                    )
                )
            try:
                await self._approval_gate.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=approved_by,
                )
            except ApprovalRequiredError as exc:
                logger.warning(
                    "decompose_control_plane_approval_required",
                    wp_id=wp_id,
                    approval_id=approval_id,
                    error=str(exc),
                )
                return DecompositionApprovalWorkflowResult(
                    request_error(
                        str(exc),
                        "control_plane_approval_required",
                        wp_id=wp_id,
                    )
                )
            await decomposition.update_status(wp_id, WRITING, approved_by=approved_by)
            project_id = record.project_id
            assignee_id = record.assignee_id
            await decomposition.commit()

        staged_events: list[StagedPJMEvent] = []
        try:
            story_count, task_count = await self._write_to_openproject(
                wp_id=wp_id,
                project_id=project_id,
                assignee_id=assignee_id,
                wbs_result=wbs_result,
            )
            final_status = APPROVED if task_count > 0 or story_count > 0 else WRITE_FAILED
            completion_event = self._create_event(
                EventTypes.PM_DECOMPOSE_COMPLETED,
                {
                    "wp_id": wp_id,
                    "status": final_status,
                    "user_story_count": story_count,
                    "task_count": task_count,
                },
            )
            dev_event = self._build_dev_handoff_event(
                wp_id=wp_id,
                wbs_result=wbs_result,
                final_status=final_status,
            )

            async with self._decomposition_store.transaction() as decomposition:
                await decomposition.update_status(wp_id, final_status)
                await self._stage_event(decomposition, completion_event)
                staged_events.append(StagedPJMEvent(completion_event, wp_id=wp_id))
                if dev_event is not None:
                    await self._stage_event(decomposition, dev_event)
                    staged_events.append(StagedPJMEvent(dev_event, wp_id=wp_id))
                await decomposition.commit()
        except Exception as exc:
            logger.error("decompose_op_write_failed", wp_id=wp_id, error=str(exc))
            story_count = 0
            task_count = 0
            completion_event = self._create_event(
                EventTypes.PM_DECOMPOSE_COMPLETED,
                {
                    "wp_id": wp_id,
                    "status": "write_failed",
                    "user_story_count": story_count,
                    "task_count": task_count,
                },
            )
            try:
                async with self._decomposition_store.transaction() as decomposition:
                    await decomposition.update_status(wp_id, WRITE_FAILED)
                    await self._stage_event(decomposition, completion_event)
                    staged_events.append(StagedPJMEvent(completion_event, wp_id=wp_id))
                    await decomposition.commit()
            except Exception as inner_exc:
                logger.error(
                    "decompose_write_failed_status_update_error",
                    wp_id=wp_id,
                    error=str(inner_exc),
                )
            try:
                await self._push.send_decompose_failure(
                    wp_id=wp_id,
                    subject=wbs_result.get("summary", f"WP#{wp_id}"),
                    error_message=f"OP write failed: {exc}",
                )
            except Exception as notify_exc:
                logger.warning(
                    "write_failed_notify_error",
                    wp_id=wp_id,
                    error=str(notify_exc),
                )

        return DecompositionApprovalWorkflowResult(
            {
                "subject": wbs_result.get("summary", ""),
                "story_count": story_count,
                "task_count": task_count,
            },
            tuple(staged_events),
        )

    async def reject_decomposition(
        self,
        wp_id: WorkPackageId,
        rejected_by: str,
        reason: str = "",
    ) -> DecompositionApprovalWorkflowResult:
        rejection_reason = DecompositionRejectionReason.from_text(reason)
        async with self._decomposition_store.transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            if not record or record.status != PENDING:
                return DecompositionApprovalWorkflowResult(None)
            wbs_result = record.decompose_result or {}
            subject = wbs_result.get("summary", "")
            approval_id = wbs_result.get("control_plane_approval_id")
            if approval_id and not rejected_by:
                return DecompositionApprovalWorkflowResult(
                    request_error(
                        "rejected_by required for control-plane rejection",
                        "control_plane_rejection_resolver_required",
                        wp_id=wp_id,
                        control_plane_approval_id=approval_id,
                    )
                )
            try:
                await self._approval_gate.reject_for_sensitive_action(
                    approval_id,
                    resolved_by=rejected_by,
                )
            except ApprovalRequiredError as exc:
                logger.warning(
                    "decompose_control_plane_rejection_required",
                    wp_id=wp_id,
                    approval_id=approval_id,
                    error=str(exc),
                )
                return DecompositionApprovalWorkflowResult(
                    request_error(
                        str(exc),
                        "control_plane_rejection_required",
                        wp_id=wp_id,
                    )
                )
            await decomposition.update_status(wp_id, REJECTED, approved_by=rejected_by)
            event = self._create_event(
                EventTypes.PM_DECOMPOSE_COMPLETED,
                {
                    "wp_id": wp_id,
                    "status": "rejected",
                    "reason": rejection_reason.to_event_payload(),
                    "user_story_count": 0,
                    "task_count": 0,
                },
            )
            await self._stage_event(decomposition, event)
            await decomposition.commit()

        logger.info(
            "decompose_rejected",
            wp_id=wp_id,
            operator_hash=hash_identifier(rejected_by),
            reason_hash=hash_identifier(rejection_reason.text),
            reason_length=rejection_reason.length,
        )
        return DecompositionApprovalWorkflowResult(
            {"subject": subject},
            (StagedPJMEvent(event, wp_id=wp_id),),
        )

    async def _write_to_openproject(
        self,
        *,
        wp_id: WorkPackageId,
        project_id: OpenProjectProjectId,
        assignee_id: int | None,
        wbs_result: dict,
    ) -> tuple[int, int]:
        if wbs_result.get("type") == "task_refinement":
            op_result = await self._op_writer.write_task_subtasks(
                parent_wp_id=wp_id,
                project_id=project_id,
                subtasks=wbs_result.get("subtasks", []),
                assignee_id=assignee_id,
            )
            story_count = 0
            task_count = op_result.get("tasks_created", 0)
        else:
            op_result = await self._op_writer.write_wbs(
                parent_wp_id=wp_id,
                project_id=project_id,
                wbs_result=wbs_result,
                assignee_id=assignee_id,
            )
            story_count = len(wbs_result.get("subtasks", []))
            task_count = sum(
                len(story.get("children", [])) for story in wbs_result.get("subtasks", [])
            )

        logger.info(
            "decompose_written_to_op",
            wp_id=wp_id,
            story_count=story_count,
            task_count=task_count,
            result_keys=sorted(op_result.keys()),
        )
        return story_count, task_count

    def _build_dev_handoff_event(
        self,
        *,
        wp_id: WorkPackageId,
        wbs_result: dict,
        final_status: DecompositionStatus,
    ) -> Event | None:
        if final_status != APPROVED:
            return None
        dev_tasks = self._build_dev_tasks(wp_id, wbs_result)
        if not dev_tasks:
            logger.warning("no_dev_tasks_extracted", wp_id=wp_id)
            return None
        return Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="pjm-agent",
            trace_id=wbs_result.get("delivery_context", {}).get("trace_id"),
            payload={
                "wp_id": wp_id,
                "tasks": dev_tasks,
                "delivery_context": wbs_result.get("delivery_context", {}),
            },
        )

    def _build_dev_tasks(self, wp_id: WorkPackageId, decompose_result: dict) -> list[dict]:
        """Build the dev-agent handoff payload from an approved decomposition."""
        if decompose_result.get("type") == "task_refinement":
            return [
                {
                    "id": wp_id * 10000 + idx + 1,
                    "title": task.get("subject", ""),
                    "description": "",
                    "estimated_hours": task.get("estimated_hours", 8),
                    "parent_story": "",
                    "related_files": [],
                }
                for idx, task in enumerate(decompose_result.get("subtasks", []))
            ]

        dev_tasks = []
        child_idx = 0
        for story in decompose_result.get("subtasks", []):
            for child in story.get("children", []):
                child_idx += 1
                dev_tasks.append(
                    {
                        "id": wp_id * 10000 + child_idx,
                        "title": child.get("subject", ""),
                        "description": "",
                        "estimated_hours": child.get("estimated_hours", 8),
                        "parent_story": story.get("subject", ""),
                        "related_files": [],
                    }
                )
        return dev_tasks

    async def _stage_event(
        self,
        transaction: PJMDecompositionTransaction,
        event: Event,
    ) -> None:
        await transaction.stage_event(event)
