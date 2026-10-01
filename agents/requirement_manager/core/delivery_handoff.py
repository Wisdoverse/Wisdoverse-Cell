"""Application handoff with local atomic mapping/outbox and no platform writes."""

import hashlib
import json
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.schemas.event_payloads import SyncTaskNeedsDecomposePayload
from shared.utils.logger import get_logger

from .domain.delivery_handoff import (
    ConfirmedRequirementSnapshot,
    DeliveryHandoffCommand,
    DeliveryHandoffReceipt,
    DeliveryReviewSnapshot,
)

logger = get_logger("requirement_manager.delivery_handoff")


class DeliveryHandoffTransaction(Protocol):
    async def get_requirement(self, requirement_id: str) -> ConfirmedRequirementSnapshot | None: ...
    async def get_receipt(self, requirement_id: str) -> DeliveryHandoffReceipt | None: ...
    async def save(self, receipt: DeliveryHandoffReceipt, event: Event) -> None: ...


class DeliveryHandoffStore(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[DeliveryHandoffTransaction]: ...


class DeliveryContextVerifier(Protocol):
    async def verify(self, command: DeliveryHandoffCommand) -> None: ...


class DeliveryHandoffUseCase:
    def __init__(
        self,
        store: DeliveryHandoffStore,
        *,
        company_id: str,
        context_verifier: DeliveryContextVerifier,
    ) -> None:
        self._store = store
        self._company_id = company_id
        self._context_verifier = context_verifier

    async def review(self, requirement_id: str) -> DeliveryReviewSnapshot:
        async with self._store.transaction() as tx:
            requirement = await tx.get_requirement(requirement_id)
            if requirement is None:
                raise ValueError("requirement_not_found")
            return DeliveryReviewSnapshot(
                requirement_id=requirement.requirement_id,
                company_id=self._company_id,
                title=requirement.title,
                description=requirement.description,
                status=requirement.status,
                confirmed_by=requirement.confirmed_by,
                requirement_hash=requirement.content_hash,
            )

    async def execute(
        self,
        requirement_id: str,
        command: DeliveryHandoffCommand,
        *,
        reviewed_by: str,
        idempotency_key: str,
        trace_id: str | None,
    ) -> DeliveryHandoffReceipt:
        if command.company_id != self._company_id:
            raise ValueError("handoff_company_mismatch")
        if not reviewed_by or idempotency_key != f"requirement-delivery:{requirement_id}":
            raise ValueError("handoff_idempotency_or_actor_invalid")
        logger.info(
            "requirement_delivery_review_started",
            agent_id="requirement-manager",
            company_id=command.company_id,
            requirement_id=requirement_id,
            goal_id=command.goal_id,
            work_item_id=command.work_item_id,
            trace_id=trace_id,
        )
        digest = hashlib.sha256(
            json.dumps(command.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        async with self._store.transaction() as tx:
            requirement = await tx.get_requirement(requirement_id)
            if requirement is None:
                raise ValueError("requirement_not_found")
            existing = await tx.get_receipt(requirement_id)
            if existing is not None:
                if existing.command_hash != digest or existing.company_id != command.company_id:
                    raise ValueError("handoff_mapping_conflict")
                return existing
            requirement.assert_reviewed(command)
            await self._context_verifier.verify(command)
            event_id = "evt_" + hashlib.sha256((requirement_id + digest).encode()).hexdigest()[:26]
            payload = SyncTaskNeedsDecomposePayload(
                wp_id=command.wp_id,
                project_id=command.project_id,
                subject=requirement.title,
                description=requirement.description,
                wp_type="Feature",
                project_name=command.project_name,
                company_id=command.company_id,
                requirement_id=requirement_id,
                requirement_hash=command.requirement_hash,
                goal_id=command.goal_id,
                work_item_id=command.work_item_id,
            )
            event = Event(
                event_id=event_id,
                event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
                source_agent="requirement-manager",
                payload=payload.model_dump(mode="json"),
                metadata=EventMetadata(trace_id=trace_id, correlation_id=requirement_id),
            )
            receipt = DeliveryHandoffReceipt(
                requirement_id=requirement_id,
                event_id=event_id,
                command_hash=digest,
                reviewed_by=reviewed_by,
                review_reason=command.reason.strip(),
                **command.model_dump(exclude={"schema_version", "reason", "project_name"}),
            )
            await tx.save(receipt, event)
        logger.info(
            "requirement_delivery_queued",
            company_id=command.company_id,
            agent_id="requirement-manager",
            requirement_id=requirement_id,
            work_item_id=command.work_item_id,
            goal_id=command.goal_id,
            trace_id=trace_id,
            event_id=event_id,
        )
        return receipt
