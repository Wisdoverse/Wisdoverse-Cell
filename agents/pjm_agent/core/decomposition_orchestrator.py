"""Decomposition workflow orchestration for PMAgent."""

from shared.control_plane import (
    ApprovalCategory,
    ApprovalGateService,
)
from shared.core import (
    EventPublisher,
    FeishuMessengerPort,
    OpenProjectWorkPackagePort,
    request_error,
)
from shared.observability.outbox import record_outbox_pending_age
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import DecomposePayload
from .card_ports import PJMCardRendererPort
from .config import PJMCoreConfig
from .decompose import DecomposeError, DecomposeService
from .decomposition_approval_workflow import DecompositionApprovalWorkflow
from .decomposition_ports import PJMDecompositionStore, PJMDecompositionTransaction
from .domain.lifecycle.decomposition_lifecycle import (
    APPROVED,
    FAILED,
    PENDING,
    REJECTED,
    WRITE_FAILED,
    WRITING,
)
from .op_writer import OPWriterService
from .outbox_ports import PJMEventOutboxStore
from .push_service import PushService

# Decomposition statuses that indicate the record already exists in some
# active state. Reused by the existence check that rejects re-trigger.
_EXISTING_BLOCKING_STATUSES: tuple[str, ...] = (PENDING, WRITING, APPROVED, WRITE_FAILED)

# Decomposition statuses from which the record can still be re-decomposed.
# Reused by retry paths that reset the record to pending.
_RECOVERABLE_STATUSES: tuple[str, ...] = (FAILED, REJECTED, WRITE_FAILED)

logger = get_logger("pjm_agent.decomposition_orchestrator")


class DecompositionOrchestrator:
    """Orchestrates work-package decomposition: decompose, approve, reject."""

    def __init__(
        self,
        db_manager: object,
        op_writer: OPWriterService,
        decompose_service: DecomposeService,
        push_service: PushService,
        create_event_fn,
        event_publisher: EventPublisher,
        op_client: OpenProjectWorkPackagePort | None = None,
        messenger: FeishuMessengerPort | None = None,
        card_renderer: PJMCardRendererPort | None = None,
        approval_gate: ApprovalGateService | None = None,
        outbox_store: PJMEventOutboxStore | None = None,
        decomposition_store: PJMDecompositionStore | None = None,
        config: PJMCoreConfig | None = None,
    ):
        self._op_writer = op_writer
        self._decompose = decompose_service
        self._push = push_service
        self._create_event = create_event_fn
        self._event_publisher = event_publisher
        self._op = op_client
        self._messenger = messenger
        self._card_renderer = card_renderer
        self._approval_gate = approval_gate or ApprovalGateService(source_agent_id="pjm-agent")
        self._outbox_store = outbox_store
        self._decomposition_store = decomposition_store
        self._config = config or PJMCoreConfig()

    def _require_outbox_store(self) -> PJMEventOutboxStore:
        if self._outbox_store is None:
            raise RuntimeError("pjm_outbox_store_not_configured")
        return self._outbox_store

    def _require_decomposition_store(self) -> PJMDecompositionStore:
        if self._decomposition_store is None:
            raise RuntimeError("pjm_decomposition_store_not_configured")
        return self._decomposition_store

    def _approval_workflow(self) -> DecompositionApprovalWorkflow:
        return DecompositionApprovalWorkflow(
            decomposition_store=self._require_decomposition_store(),
            approval_gate=self._approval_gate,
            op_writer=self._op_writer,
            push_service=self._push,
            create_event_fn=self._create_event,
        )

    async def publish_pending_pjm_events(self, limit: int = 100) -> dict[str, int]:
        """
        Retry pending PJM outbox events.

        This use case keeps retry dispatch reusable from a runtime plugin,
        future admin endpoint, or standalone worker.
        """
        rows = await self._require_outbox_store().list_pending(limit=limit)
        record_outbox_pending_age("pjm-agent", rows)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            try:
                ok = await self._event_publisher.publish(event)
                if not ok:
                    raise RuntimeError("pjm_event_publish_rejected")
                await self._mark_pjm_event_published(event)
                published += 1
            except Exception as exc:
                await self._mark_pjm_event_failed(event, exc)
                failed += 1

        logger.info(
            "pjm_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def _stage_pjm_event(
        self,
        transaction: PJMDecompositionTransaction,
        event: Event,
    ) -> Event:
        """Persist an integration event in the local PJM outbox."""
        await transaction.stage_event(event)
        return event

    async def publish_event_via_outbox(
        self,
        event: Event,
        *,
        wp_id: int | None = None,
    ) -> None:
        """Stage a PJM integration event, then publish after the local commit."""
        await self._require_outbox_store().add(event)
        await self._publish_staged_pjm_event(event, wp_id=wp_id)

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a PJM outbox row."""
        return Event(
            event_id=row.event_id,
            event_type=row.event_type,
            timestamp=row.created_at,
            source_agent=row.source_agent,
            payload=row.payload,
            schema_version=row.schema_version,
            metadata=EventMetadata(
                trace_id=row.trace_id,
                correlation_id=row.correlation_id,
                retry_count=row.retry_count,
            ),
        )

    async def _publish_staged_pjm_event(
        self,
        event: Event,
        *,
        wp_id: int | None = None,
    ) -> None:
        """Publish an event already persisted in the PJM outbox."""
        try:
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("pjm_event_publish_rejected")
            await self._mark_pjm_event_published(event)
            logger.info(
                "pjm_event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                wp_id=wp_id,
            )
        except Exception as exc:
            await self._mark_pjm_event_failed(event, exc)
            logger.error(
                "pjm_event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                wp_id=wp_id,
                error=str(exc),
            )

    async def _mark_pjm_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published outbox event."""
        try:
            await self._require_outbox_store().mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "pjm_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_pjm_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an outbox event publish attempt."""
        try:
            await self._require_outbox_store().mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "pjm_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )

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
            "decompose_start", wp_id=wp_id, subject=subject, wp_type=wp_type, trace_id=trace_id
        )

        # Dedup check
        async with self._require_decomposition_store().transaction() as decomposition:
            existing = await decomposition.get_by_wp_id(wp_id)
            if existing and existing.status in _EXISTING_BLOCKING_STATUSES:
                logger.info("decompose_skip_duplicate", wp_id=wp_id, status=existing.status)
                return []
            # Allow failed/rejected to retry — delete old record
            if existing:
                await decomposition.delete_by_wp_id(wp_id)
                await decomposition.commit()

        # Branch: Task detail check vs Feature/Epic decomposition
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

        # Run decomposition (Feature/Epic)
        try:
            result = await self._decompose.decompose(
                wp_id=wp_id,
                subject=subject,
                description=description,
                wp_type=wp_type,
                project_name=project_name,
                assignee=assignee,
            )
        except DecomposeError as e:
            logger.error("decompose_failed", wp_id=wp_id, error=str(e), trace_id=trace_id)
            try:
                async with self._require_decomposition_store().transaction() as decomposition:
                    await decomposition.create(
                        wp_id=wp_id,
                        project_id=project_id,
                        decompose_result=request_error(
                            str(e),
                            "pm.decomposition_failed",
                        ),
                        assignee_id=assignee_id,
                    )
                    await decomposition.update_status(wp_id, FAILED)
                    await decomposition.commit()
            except Exception:
                logger.error("decompose_failed_save_error", wp_id=wp_id)
            # Notify user about decomposition failure via Feishu
            try:
                await self._push.send_decompose_failure(
                    wp_id=wp_id,
                    subject=subject,
                    error_message=str(e),
                )
            except Exception as push_err:
                logger.warning("decompose_failure_notify_failed", wp_id=wp_id, error=str(push_err))
            return [
                self._create_event(
                    EventTypes.PM_DECOMPOSE_COMPLETED,
                    {"wp_id": wp_id, "status": "rejected", "user_story_count": 0, "task_count": 0},
                    trace_id=trace_id,
                )
            ]

        # Save to DB
        result_dict = result.model_dump()
        approval_id = await self._request_decomposition_approval(
            wp_id=wp_id,
            project_id=project_id,
            subject=subject,
            result_dict=result_dict,
            trace_id=trace_id,
        )
        if approval_id:
            result_dict["control_plane_approval_id"] = approval_id
        try:
            async with self._require_decomposition_store().transaction() as decomposition:
                await decomposition.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=result_dict,
                    assignee_id=assignee_id,
                )
                await decomposition.commit()
        except Exception as e:
            logger.error("decompose_save_failed", wp_id=wp_id, error=str(e))

        story_count = len(result.subtasks)
        task_count = sum(len(s.children) for s in result.subtasks)
        logger.info(
            "decompose_done", wp_id=wp_id, stories=story_count, tasks=task_count, trace_id=trace_id
        )

        # Send approval card to Feishu
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
                    id_type = "open_id" if decompose_notify_id.startswith("ou_") else "chat_id"
                    await self._messenger.send_card(
                        receive_id=decompose_notify_id,
                        receive_id_type=id_type,
                        card=card,
                    )
                    logger.info("decompose_card_sent", wp_id=wp_id)
        except Exception as e:
            logger.error("decompose_card_send_failed", wp_id=wp_id, error=str(e))

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
        """Check if a Task is detailed enough; if not, decompose into sub-tasks."""
        try:
            check_result = await self._decompose.check_task_detail(
                wp_id=wp_id,
                subject=subject,
                description=description,
                project_name=project_name,
                assignee=assignee,
            )
        except DecomposeError as e:
            logger.error("task_check_failed", wp_id=wp_id, error=str(e), trace_id=trace_id)
            try:
                async with self._require_decomposition_store().transaction() as decomposition:
                    await decomposition.create(
                        wp_id=wp_id,
                        project_id=project_id,
                        decompose_result=request_error(
                            str(e),
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

        # Task not detailed enough — save and send approval card
        result_dict = {
            "type": "task_refinement",
            "reason": check_result.reason,
            "subtasks": [t.model_dump() for t in check_result.subtasks],
        }
        approval_id = await self._request_decomposition_approval(
            wp_id=wp_id,
            project_id=project_id,
            subject=subject,
            result_dict=result_dict,
            trace_id=trace_id,
        )
        if approval_id:
            result_dict["control_plane_approval_id"] = approval_id
        try:
            async with self._require_decomposition_store().transaction() as decomposition:
                await decomposition.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=result_dict,
                    assignee_id=assignee_id,
                )
                await decomposition.commit()
        except Exception as e:
            logger.error("task_check_save_failed", wp_id=wp_id, error=str(e))

        subtask_count = len(check_result.subtasks)
        logger.info(
            "task_check_needs_refinement", wp_id=wp_id, subtasks=subtask_count, trace_id=trace_id
        )

        # Send refinement approval card
        try:
            decompose_notify_id = self._config.decompose_notification_chat_id
            if decompose_notify_id and self._messenger:
                if self._card_renderer is None:
                    logger.warning("task_refinement_card_renderer_missing", wp_id=wp_id)
                else:
                    card = self._card_renderer.build_task_refinement_approval_card(
                        wp_id=wp_id,
                        subject=subject,
                        reason=check_result.reason,
                        subtasks=[t.model_dump() for t in check_result.subtasks],
                    )
                    id_type = "open_id" if decompose_notify_id.startswith("ou_") else "chat_id"
                    await self._messenger.send_card(
                        receive_id=decompose_notify_id,
                        receive_id_type=id_type,
                        card=card,
                    )
                    logger.info("task_refinement_card_sent", wp_id=wp_id)
        except Exception as e:
            logger.error("task_refinement_card_send_failed", wp_id=wp_id, error=str(e))

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

    async def approve_decomposition(self, wp_id: int, approved_by: str) -> dict | None:
        result = await self._approval_workflow().approve_decomposition(
            wp_id,
            approved_by,
        )
        for staged_event in result.staged_events:
            await self._publish_staged_pjm_event(staged_event.event, wp_id=staged_event.wp_id)
        return result.response

    async def _request_decomposition_approval(
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

    async def retry_decompose(self, wp_id: int) -> dict:
        """Retry a failed/rejected decomposition by re-fetching WP data from OP."""
        if not wp_id:
            return request_error("wp_id is required", "wp_id_required")
        async with self._require_decomposition_store().transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            if not record:
                return request_error("record not found", "pm.decomposition_not_found")
            if record.status not in _RECOVERABLE_STATUSES:
                return request_error(
                    (
                        f"cannot retry status '{record.status}', "
                        "only failed/rejected/write_failed"
                    ),
                    "pm.decomposition_retry_not_allowed",
                    status=record.status,
                )
            project_id = record.project_id
            assignee_id = record.assignee_id

        # Fetch latest WP data from OP and re-trigger
        try:
            if self._op is None:
                return request_error(
                    "openproject port not configured",
                    "openproject_port_not_configured",
                )
            wp = await self._op.get_work_package(wp_id)
            subject = wp.get("subject", "")
            description_raw = wp.get("description", {})
            description = (
                description_raw.get("raw", "") if isinstance(description_raw, dict) else ""
            )
            wp_type = wp.get("_links", {}).get("type", {}).get("title", "Feature")
            project_name = wp.get("_links", {}).get("project", {}).get("title", "")
            assignee_name = wp.get("_links", {}).get("assignee", {}).get("title", "")
        except Exception as e:
            return request_error(
                f"failed to fetch WP from OP: {e}",
                "openproject_work_package_fetch_failed",
                wp_id=wp_id,
            )

        event = Event.create(
            event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            source_agent="pjm-agent",
            payload={
                "wp_id": wp_id,
                "subject": subject,
                "description": description,
                "wp_type": wp_type,
                "project_id": project_id,
                "project_name": project_name,
                "assignee": assignee_name,
                "assignee_id": assignee_id,
            },
        )
        async with self._require_decomposition_store().transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            if not record:
                return request_error("record not found", "pm.decomposition_not_found")
            if record.status not in _RECOVERABLE_STATUSES:
                return request_error(
                    (
                        f"cannot retry status '{record.status}', "
                        "only failed/rejected/write_failed"
                    ),
                    "pm.decomposition_retry_not_allowed",
                    status=record.status,
                )
            await decomposition.delete_by_wp_id(wp_id)
            await self._stage_pjm_event(decomposition, event)
            await decomposition.commit()

        await self._publish_staged_pjm_event(event, wp_id=wp_id)
        return {"status": "retrying", "wp_id": wp_id}

    async def get_decompose(self, wp_id: int | None) -> dict:
        """Retrieve decomposition record for a given work package."""
        if not wp_id:
            return {}
        async with self._require_decomposition_store().transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            if not record:
                return {}
            return {
                "wp_id": record.wp_id,
                "project_id": record.project_id,
                "status": record.status,
                "assignee_id": record.assignee_id,
                "decompose_result": record.decompose_result,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "approved_by": record.approved_by,
            }

    async def reject_decomposition(
        self, wp_id: int, rejected_by: str, reason: str = ""
    ) -> dict | None:
        result = await self._approval_workflow().reject_decomposition(
            wp_id,
            rejected_by,
            reason,
        )
        for staged_event in result.staged_events:
            await self._publish_staged_pjm_event(staged_event.event, wp_id=staged_event.wp_id)
        return result.response
