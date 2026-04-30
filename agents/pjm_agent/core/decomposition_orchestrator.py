"""
DecompositionOrchestrator - Handles decomposition workflow for PMAgent.

Extracted from PMAgent to separate decomposition orchestration concerns
(decompose, approve, reject) from the main agent class.
"""

from shared.config import settings as app_settings
from shared.integrations.feishu.cards.decomposition import (
    build_decomposition_approval_card,
    build_task_refinement_approval_card,
)
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import get_op_client
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..db.database import DatabaseManager
from ..db.repository import DecompositionRepository
from ..models.schemas import DecomposePayload
from .decompose import DecomposeError, DecomposeService
from .op_writer import OPWriterService
from .push_service import PushService

logger = get_logger("pjm_agent.decomposition_orchestrator")


class DecompositionOrchestrator:
    """Orchestrates work-package decomposition: decompose, approve, reject."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        op_writer: OPWriterService,
        decompose_service: DecomposeService,
        push_service: PushService,
        create_event_fn,
        event_bus,
    ):
        self._db_manager = db_manager
        self._op_writer = op_writer
        self._decompose = decompose_service
        self._push = push_service
        self._create_event = create_event_fn
        self._event_bus = event_bus

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
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            existing = await repo.get_by_wp_id(wp_id)
            if existing and existing.status in ("pending", "approved"):
                logger.info("decompose_skip_duplicate", wp_id=wp_id, status=existing.status)
                return []
            # Allow failed/rejected to retry — delete old record
            if existing:
                await repo.delete_by_wp_id(wp_id)

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
                async with self._db_manager.session() as session:
                    repo = DecompositionRepository(session)
                    await repo.create(
                        wp_id=wp_id,
                        project_id=project_id,
                        decompose_result={"error": str(e)},
                        assignee_id=assignee_id,
                    )
                    await repo.update_status(wp_id, "failed")
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
        try:
            async with self._db_manager.session() as session:
                repo = DecompositionRepository(session)
                await repo.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=result_dict,
                    assignee_id=assignee_id,
                )
        except Exception as e:
            logger.error("decompose_save_failed", wp_id=wp_id, error=str(e))

        story_count = len(result.subtasks)
        task_count = sum(len(s.children) for s in result.subtasks)
        logger.info(
            "decompose_done", wp_id=wp_id, stories=story_count, tasks=task_count, trace_id=trace_id
        )

        # Send approval card to Feishu
        try:
            card = build_decomposition_approval_card(
                wp_id=wp_id,
                subject=subject,
                wbs_result=result_dict,
            )
            feishu_client = get_feishu_client()
            decompose_notify_id = (
                getattr(app_settings, "decompose_notify_open_id", "")
                or app_settings.feishu_report_chat_id
            )
            if decompose_notify_id:
                id_type = "open_id" if decompose_notify_id.startswith("ou_") else "chat_id"
                await feishu_client.send_card(
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
                async with self._db_manager.session() as session:
                    repo = DecompositionRepository(session)
                    await repo.create(
                        wp_id=wp_id,
                        project_id=project_id,
                        decompose_result={"error": str(e)},
                        assignee_id=assignee_id,
                    )
                    await repo.update_status(wp_id, "failed")
            except Exception:
                pass
            return []

        if check_result.detailed:
            logger.info("task_check_detailed", wp_id=wp_id, reason=check_result.reason)
            return []

        # Task not detailed enough — save and send approval card
        result_dict = {
            "type": "task_refinement",
            "reason": check_result.reason,
            "subtasks": [t.model_dump() for t in check_result.subtasks],
        }
        try:
            async with self._db_manager.session() as session:
                repo = DecompositionRepository(session)
                await repo.create(
                    wp_id=wp_id,
                    project_id=project_id,
                    decompose_result=result_dict,
                    assignee_id=assignee_id,
                )
        except Exception as e:
            logger.error("task_check_save_failed", wp_id=wp_id, error=str(e))

        subtask_count = len(check_result.subtasks)
        logger.info(
            "task_check_needs_refinement", wp_id=wp_id, subtasks=subtask_count, trace_id=trace_id
        )

        # Send refinement approval card
        try:
            card = build_task_refinement_approval_card(
                wp_id=wp_id,
                subject=subject,
                reason=check_result.reason,
                subtasks=[t.model_dump() for t in check_result.subtasks],
            )
            feishu_client = get_feishu_client()
            decompose_notify_id = (
                getattr(app_settings, "decompose_notify_open_id", "")
                or app_settings.feishu_report_chat_id
            )
            if decompose_notify_id:
                id_type = "open_id" if decompose_notify_id.startswith("ou_") else "chat_id"
                await feishu_client.send_card(
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
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            record = await repo.get_by_wp_id(wp_id)
            if not record or record.status != "pending":
                return None
            # Transition to "writing" before attempting OP write
            await repo.update_status(wp_id, "writing", approved_by=approved_by)
            # Extract data while session is still active
            wbs_result = record.decompose_result
            project_id = record.project_id
            assignee_id = record.assignee_id

        is_task_refinement = wbs_result.get("type") == "task_refinement"

        # Write to OpenProject
        try:
            if is_task_refinement:
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
                task_count = sum(len(s.get("children", [])) for s in wbs_result.get("subtasks", []))
            logger.info("decompose_written_to_op", wp_id=wp_id, result=op_result)
            # Write succeeded — transition to "approved"
            async with self._db_manager.session() as session:
                repo = DecompositionRepository(session)
                await repo.update_status(wp_id, "approved")
        except Exception as e:
            logger.error("decompose_op_write_failed", wp_id=wp_id, error=str(e))
            # Write failed — transition to "write_failed"
            try:
                async with self._db_manager.session() as session:
                    repo = DecompositionRepository(session)
                    await repo.update_status(wp_id, "write_failed")
            except Exception as inner_e:
                logger.error(
                    "decompose_write_failed_status_update_error", wp_id=wp_id, error=str(inner_e)
                )
            # Notify about write failure via Feishu
            try:
                await self._push.send_decompose_failure(
                    wp_id=wp_id,
                    subject=wbs_result.get("summary", f"WP#{wp_id}"),
                    error_message=f"OP write failed: {e}",
                )
            except Exception as notify_err:
                logger.warning("write_failed_notify_error", wp_id=wp_id, error=str(notify_err))
            story_count = 0
            task_count = 0

        # Publish event with final status
        final_status = "approved" if task_count > 0 or story_count > 0 else "write_failed"
        event = self._create_event(
            EventTypes.PM_DECOMPOSE_COMPLETED,
            {
                "wp_id": wp_id,
                "status": final_status,
                "user_story_count": story_count,
                "task_count": task_count,
            },
        )
        try:
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error("decompose_event_publish_failed", wp_id=wp_id, error=str(e))

        # Publish tasks-ready-for-dev event when OPWriter succeeded
        if final_status == "approved":
            decompose_result = wbs_result
            is_refinement = decompose_result.get("type") == "task_refinement"

            if is_refinement:
                # Flat subtask list: each item is a WBSTask with subject/estimated_hours
                # Generate unique IDs per child to avoid dev_agent_tasks.wp_id collision
                dev_tasks = [
                    {
                        "id": wp_id * 10000 + idx + 1,
                        "title": t.get("subject", ""),
                        "description": "",
                        "estimated_hours": t.get("estimated_hours", 8),
                        "parent_story": "",
                        "related_files": [],
                    }
                    for idx, t in enumerate(decompose_result.get("subtasks", []))
                ]
            else:
                # Full WBS: subtasks are WBSSubtask with subject/children
                # Generate unique IDs per child to avoid dev_agent_tasks.wp_id collision
                dev_tasks = []
                child_idx = 0
                for story in decompose_result.get("subtasks", []):
                    for child in story.get("children", []):
                        child_idx += 1
                        dev_tasks.append({
                            "id": wp_id * 10000 + child_idx,
                            "title": child.get("subject", ""),
                            "description": "",
                            "estimated_hours": child.get("estimated_hours", 8),
                            "parent_story": story.get("subject", ""),
                            "related_files": [],
                        })

            if dev_tasks:
                dev_event = Event.create(
                    event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
                    source_agent="pjm-agent",
                    payload={
                        "wp_id": wp_id,
                        "tasks": dev_tasks,
                    },
                )
                try:
                    await self._event_bus.publish(dev_event)
                    logger.info(
                        "tasks_ready_for_dev_published",
                        wp_id=wp_id,
                        task_count=len(dev_tasks),
                    )
                except Exception as e:
                    logger.error(
                        "tasks_ready_for_dev_publish_failed",
                        wp_id=wp_id,
                        error=str(e),
                        exc_info=True,
                    )
            else:
                logger.warning("no_dev_tasks_extracted", wp_id=wp_id)

        return {
            "subject": wbs_result.get("summary", ""),
            "story_count": story_count,
            "task_count": task_count,
        }

    async def retry_decompose(self, wp_id: int) -> dict:
        """Retry a failed/rejected decomposition by re-fetching WP data from OP."""
        if not wp_id:
            return {"error": "wp_id is required"}
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            record = await repo.get_by_wp_id(wp_id)
            if not record:
                return {"error": "record not found"}
            if record.status not in ("failed", "rejected"):
                return {"error": f"cannot retry status '{record.status}', only failed/rejected"}
            project_id = record.project_id
            assignee_id = record.assignee_id
            await repo.delete_by_wp_id(wp_id)

        # Fetch latest WP data from OP and re-trigger
        try:
            op_client = get_op_client()
            wp = await op_client.get_work_package(wp_id)
            subject = wp.get("subject", "")
            description_raw = wp.get("description", {})
            description = (
                description_raw.get("raw", "") if isinstance(description_raw, dict) else ""
            )
            wp_type = wp.get("_links", {}).get("type", {}).get("title", "Feature")
            project_name = wp.get("_links", {}).get("project", {}).get("title", "")
            assignee_name = wp.get("_links", {}).get("assignee", {}).get("title", "")
        except Exception as e:
            return {"error": f"failed to fetch WP from OP: {e}"}

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
        await self._event_bus.publish(event)
        return {"status": "retrying", "wp_id": wp_id}

    async def get_decompose(self, wp_id: int | None) -> dict:
        """Retrieve decomposition record for a given work package."""
        if not wp_id:
            return {}
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            record = await repo.get_by_wp_id(wp_id)
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
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            record = await repo.get_by_wp_id(wp_id)
            if not record or record.status != "pending":
                return None
            subject = (record.decompose_result or {}).get("summary", "")
            await repo.update_status(wp_id, "rejected", approved_by=rejected_by)

        logger.info("decompose_rejected", wp_id=wp_id, by=rejected_by, reason=reason)
        event = self._create_event(
            EventTypes.PM_DECOMPOSE_COMPLETED,
            {
                "wp_id": wp_id,
                "status": "rejected",
                "reason": reason,
                "user_story_count": 0,
                "task_count": 0,
            },
        )
        try:
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error("decompose_event_publish_failed", wp_id=wp_id, error=str(e))
        return {"subject": subject}
