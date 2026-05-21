"""Decomposition workflow orchestration for PMAgent."""

from shared.control_plane import ApprovalGateService
from shared.core import (
    EventPublisher,
    FeishuMessengerPort,
    OpenProjectWorkPackagePort,
)
from shared.observability.outbox import record_outbox_pending_age
from shared.schemas.event import Event, EventMetadata
from shared.utils.logger import get_logger

from .card_ports import PJMCardRendererPort
from .config import PJMCoreConfig
from .decompose import DecomposeService
from .decomposition_approval_workflow import DecompositionApprovalWorkflow
from .decomposition_ports import PJMDecompositionStore
from .decomposition_recovery_workflow import DecompositionRecoveryWorkflow
from .decomposition_request_workflow import DecompositionRequestWorkflow
from .op_writer import OPWriterService
from .outbox_ports import PJMEventOutboxStore
from .push_service import PushService

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

    def _request_workflow(self) -> DecompositionRequestWorkflow:
        return DecompositionRequestWorkflow(
            decomposition_store=self._require_decomposition_store(),
            decompose_service=self._decompose,
            push_service=self._push,
            approval_gate=self._approval_gate,
            create_event_fn=self._create_event,
            config=self._config,
            messenger=self._messenger,
            card_renderer=self._card_renderer,
        )

    def _recovery_workflow(self) -> DecompositionRecoveryWorkflow:
        return DecompositionRecoveryWorkflow(
            decomposition_store=self._decomposition_store,
            op_client=self._op,
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
        return await self._request_workflow().handle_decompose(event)

    async def approve_decomposition(self, wp_id: int, approved_by: str) -> dict | None:
        result = await self._approval_workflow().approve_decomposition(
            wp_id,
            approved_by,
        )
        for staged_event in result.staged_events:
            await self._publish_staged_pjm_event(staged_event.event, wp_id=staged_event.wp_id)
        return result.response

    async def retry_decompose(self, wp_id: int) -> dict:
        result = await self._recovery_workflow().retry_decompose(wp_id)
        for staged_event in result.staged_events:
            await self._publish_staged_pjm_event(staged_event.event, wp_id=staged_event.wp_id)
        return result.response

    async def get_decompose(self, wp_id: int | None) -> dict:
        return await self._recovery_workflow().get_decompose(wp_id)

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
