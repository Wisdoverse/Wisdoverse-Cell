"""Request-time decomposition workflow for PJM work packages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from shared.control_plane import ApprovalCategory, ApprovalGateService
from shared.core import FeishuMessengerPort, request_error
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import DecomposePayload, TaskCheckResult, WBSResult
from .card_ports import PJMCardRendererPort
from .config import PJMCoreConfig
from .decompose import DecomposeError
from .decomposition_ports import PJMDecompositionStore
from .domain.lifecycle.decomposition_lifecycle import (
    APPROVED,
    FAILED,
    PENDING,
    WRITE_FAILED,
    WRITING,
)

logger = get_logger("pjm_agent.decomposition_request_workflow")

_EXISTING_BLOCKING_STATUSES: tuple[str, ...] = (PENDING, WRITING, APPROVED, WRITE_FAILED)


class PJMDecompositionEnginePort(Protocol):
    async def decompose(
        self,
        *,
        wp_id: int,
        subject: str,
        description: str,
        wp_type: str,
        project_name: str = "",
        assignee: str = "",
    ) -> WBSResult:
        """Generate a work-breakdown structure from a work package."""

    async def check_task_detail(
        self,
        *,
        wp_id: int,
        subject: str,
        description: str,
        project_name: str = "",
        assignee: str = "",
    ) -> TaskCheckResult:
        """Check whether a task needs refinement subtasks."""


class PJMDecompositionFailurePushPort(Protocol):
    async def send_decompose_failure(
        self,
        wp_id: int,
        subject: str,
        error_message: str,
    ) -> bool:
        """Notify operators that decomposition failed before approval."""


class DecompositionRequestWorkflow:
    """Owns decomposition request intake, persistence, approval, and cards."""

    def __init__(
        self,
        *,
        decomposition_store: PJMDecompositionStore,
        decompose_service: PJMDecompositionEnginePort,
        push_service: PJMDecompositionFailurePushPort,
        approval_gate: ApprovalGateService,
        create_event_fn: Callable[..., Event],
        config: PJMCoreConfig,
        messenger: FeishuMessengerPort | None = None,
        card_renderer: PJMCardRendererPort | None = None,
    ) -> None:
        self._decomposition_store = decomposition_store
        self._decompose = decompose_service
        self._push = push_service
        self._approval_gate = approval_gate
        self._create_event = create_event_fn
        self._config = config
        self._messenger = messenger
        self._card_renderer = card_renderer

    async def handle_decompose(self, event: Event) -> list[Event]:
        """Handle a SYNC_TASK_NEEDS_DECOMPOSE event."""
        payload = DecomposePayload.model_validate(event.payload)
        wp_id = payload.wp_id
        project_id = payload.project_id
        subject = payload.subject
        description = payload.description
        wp_type = payload.wp_type
        project_name = payload.project_name
        assignee = payload.assignee
        assignee_id = payload.assignee_id
        trace_id = event.metadata.trace_id

        logger.info(
            "decompose_start",
            wp_id=wp_id,
            subject=subject,
            wp_type=wp_type,
            trace_id=trace_id,
        )

        async with self._decomposition_store.transaction() as decomposition:
            existing = await decomposition.get_by_wp_id(wp_id)
            if existing and existing.status in _EXISTING_BLOCKING_STATUSES:
                logger.info("decompose_skip_duplicate", wp_id=wp_id, status=existing.status)
                return []
            if existing:
                await decomposition.delete_by_wp_id(wp_id)
                await decomposition.commit()

        if wp_type == "Task":
            return await self._handle_task_check(
                wp_id=wp_id,
                project_id=project_id,
                subject=subject,
                description=description,
                project_name=project_name,
                assignee=assignee,
                assignee_id=assignee_id,
                trace_id=trace_id,
            )

        try:
            result = await self._decompose.decompose(
                wp_id=wp_id,
                subject=subject,
                description=description,
                wp_type=wp_type,
                project_name=project_name,
                assignee=assignee,
            )
        except DecomposeError as exc:
            return await self._handle_decompose_failure(
                wp_id=wp_id,
                project_id=project_id,
                subject=subject,
                assignee_id=assignee_id,
                trace_id=trace_id,
                error=exc,
            )

        result_dict = result.model_dump()
        approval_id = await self.request_decomposition_approval(
            wp_id=wp_id,
            project_id=project_id,
            subject=subject,
            result_dict=result_dict,
            trace_id=trace_id,
        )
        if approval_id:
            result_dict["control_plane_approval_id"] = approval_id
        try:
            async with self._decomposition_store.transaction() as decomposition:
                await decomposition.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=result_dict,
                    assignee_id=assignee_id,
                )
                await decomposition.commit()
        except Exception as exc:
            logger.error("decompose_save_failed", wp_id=wp_id, error=str(exc))

        story_count = len(result.subtasks)
        task_count = sum(len(story.children) for story in result.subtasks)
        logger.info(
            "decompose_done",
            wp_id=wp_id,
            stories=story_count,
            tasks=task_count,
            trace_id=trace_id,
        )
        await self._send_decomposition_approval_card(
            wp_id=wp_id,
            subject=subject,
            result_dict=result_dict,
        )
        return [
            self._create_event(
                EventTypes.PM_DECOMPOSE_COMPLETED,
                {
                    "wp_id": wp_id,
                    "status": "pending",
                    "user_story_count": story_count,
                    "task_count": task_count,
                },
                trace_id=trace_id,
            )
        ]

    async def request_decomposition_approval(
        self,
        *,
        wp_id: int,
        project_id: int,
        subject: str,
        result_dict: dict,
        trace_id: str | None,
    ) -> str | None:
        try:
            approval = await self._approval_gate.request_approval(
                category=ApprovalCategory.CUSTOMER,
                proposed_action=f"Write approved decomposition for OP WP#{wp_id}",
                reason=subject,
                risk=(
                    "Creates or refines OpenProject work packages from an AI-generated "
                    "decomposition."
                ),
                rollback_note=(
                    "Reject the decomposition before OP write; after write, revert created "
                    "OpenProject work packages manually."
                ),
                affected_resources=[
                    f"openproject:project:{project_id}",
                    f"openproject:wp:{wp_id}",
                ],
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error(
                "decompose_approval_request_failed",
                wp_id=wp_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._approval_gate.enforced:
                raise
            return None

        if approval is None:
            return None
        result_dict["approval_requested_at"] = approval.created_at.isoformat()
        return approval.approval_id

    async def _handle_task_check(
        self,
        wp_id: int,
        project_id: int,
        subject: str,
        description: str,
        project_name: str,
        assignee: str,
        assignee_id: int | None,
        trace_id: str | None,
    ) -> list[Event]:
        try:
            check_result = await self._decompose.check_task_detail(
                wp_id=wp_id,
                subject=subject,
                description=description,
                project_name=project_name,
                assignee=assignee,
            )
        except DecomposeError as exc:
            logger.error("task_check_failed", wp_id=wp_id, error=str(exc), trace_id=trace_id)
            try:
                async with self._decomposition_store.transaction() as decomposition:
                    await decomposition.create(
                        wp_id=wp_id,
                        project_id=project_id,
                        decompose_result=request_error(
                            str(exc),
                            "pm.task_detail_check_failed",
                        ),
                        assignee_id=assignee_id,
                    )
                    await decomposition.update_status(wp_id, FAILED)
                    await decomposition.commit()
            except Exception:
                pass
            return []

        if check_result.detailed:
            logger.info(
                "task_check_detailed",
                wp_id=wp_id,
                reason_hash=hash_identifier(check_result.reason),
                reason_length=len(check_result.reason),
            )
            return []

        return await self._record_task_refinement(
            wp_id=wp_id,
            project_id=project_id,
            subject=subject,
            assignee_id=assignee_id,
            trace_id=trace_id,
            check_result=check_result,
        )

    async def _record_task_refinement(
        self,
        *,
        wp_id: int,
        project_id: int,
        subject: str,
        assignee_id: int | None,
        trace_id: str | None,
        check_result: TaskCheckResult,
    ) -> list[Event]:
        subtasks = [task.model_dump() for task in check_result.subtasks]
        result_dict = {
            "type": "task_refinement",
            "reason": check_result.reason,
            "subtasks": subtasks,
        }
        approval_id = await self.request_decomposition_approval(
            wp_id=wp_id,
            project_id=project_id,
            subject=subject,
            result_dict=result_dict,
            trace_id=trace_id,
        )
        if approval_id:
            result_dict["control_plane_approval_id"] = approval_id
        try:
            async with self._decomposition_store.transaction() as decomposition:
                await decomposition.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=result_dict,
                    assignee_id=assignee_id,
                )
                await decomposition.commit()
        except Exception as exc:
            logger.error("task_check_save_failed", wp_id=wp_id, error=str(exc))

        subtask_count = len(check_result.subtasks)
        logger.info(
            "task_check_needs_refinement",
            wp_id=wp_id,
            subtasks=subtask_count,
            trace_id=trace_id,
        )
        await self._send_task_refinement_approval_card(
            wp_id=wp_id,
            subject=subject,
            reason=check_result.reason,
            subtasks=subtasks,
        )
        return [
            self._create_event(
                EventTypes.PM_DECOMPOSE_COMPLETED,
                {
                    "wp_id": wp_id,
                    "status": "pending",
                    "user_story_count": 0,
                    "task_count": subtask_count,
                },
                trace_id=trace_id,
            )
        ]

    async def _handle_decompose_failure(
        self,
        *,
        wp_id: int,
        project_id: int,
        subject: str,
        assignee_id: int | None,
        trace_id: str | None,
        error: DecomposeError,
    ) -> list[Event]:
        logger.error("decompose_failed", wp_id=wp_id, error=str(error), trace_id=trace_id)
        try:
            async with self._decomposition_store.transaction() as decomposition:
                await decomposition.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=request_error(
                        str(error),
                        "pm.decomposition_failed",
                    ),
                    assignee_id=assignee_id,
                )
                await decomposition.update_status(wp_id, FAILED)
                await decomposition.commit()
        except Exception:
            logger.error("decompose_failed_save_error", wp_id=wp_id)
        try:
            await self._push.send_decompose_failure(
                wp_id=wp_id,
                subject=subject,
                error_message=str(error),
            )
        except Exception as push_exc:
            logger.warning(
                "decompose_failure_notify_failed",
                wp_id=wp_id,
                error=str(push_exc),
            )
        return [
            self._create_event(
                EventTypes.PM_DECOMPOSE_COMPLETED,
                {"wp_id": wp_id, "status": "rejected", "user_story_count": 0, "task_count": 0},
                trace_id=trace_id,
            )
        ]

    async def _send_decomposition_approval_card(
        self,
        *,
        wp_id: int,
        subject: str,
        result_dict: dict,
    ) -> None:
        try:
            decompose_notify_id = self._config.decompose_notification_chat_id
            if decompose_notify_id and self._messenger:
                if self._card_renderer is None:
                    logger.warning("decompose_card_renderer_missing", wp_id=wp_id)
                else:
                    card = self._card_renderer.build_decomposition_approval_card(
                        wp_id=wp_id,
                        subject=subject,
                        wbs_result=result_dict,
                    )
                    await self._messenger.send_card(
                        receive_id=decompose_notify_id,
                        receive_id_type=self._receive_id_type(decompose_notify_id),
                        card=card,
                    )
                    logger.info("decompose_card_sent", wp_id=wp_id)
        except Exception as exc:
            logger.error("decompose_card_send_failed", wp_id=wp_id, error=str(exc))

    async def _send_task_refinement_approval_card(
        self,
        *,
        wp_id: int,
        subject: str,
        reason: str,
        subtasks: list[dict],
    ) -> None:
        try:
            decompose_notify_id = self._config.decompose_notification_chat_id
            if decompose_notify_id and self._messenger:
                if self._card_renderer is None:
                    logger.warning("task_refinement_card_renderer_missing", wp_id=wp_id)
                else:
                    card = self._card_renderer.build_task_refinement_approval_card(
                        wp_id=wp_id,
                        subject=subject,
                        reason=reason,
                        subtasks=subtasks,
                    )
                    await self._messenger.send_card(
                        receive_id=decompose_notify_id,
                        receive_id_type=self._receive_id_type(decompose_notify_id),
                        card=card,
                    )
                    logger.info("task_refinement_card_sent", wp_id=wp_id)
        except Exception as exc:
            logger.error("task_refinement_card_send_failed", wp_id=wp_id, error=str(exc))

    def _receive_id_type(self, receive_id: str) -> str:
        return "open_id" if receive_id.startswith("ou_") else "chat_id"
