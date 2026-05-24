"""Application workflow for Requirement mutation commands."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from shared.core.identifiers import OpenQuestionId, RequirementId
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models import OpenQuestion, Requirement
from .domain.aggregate_consistency import (
    FEEDBACK_RECORD,
    OPEN_QUESTION,
    REQUIREMENT,
    REQUIREMENT_EVENT_OUTBOX,
    RequirementAggregateConsistencyPolicy,
)
from .domain.lifecycle.requirement_lifecycle import record_updated
from .feedback_learning import FeedbackLearningService
from .unit_of_work_ports import RequirementUnitOfWork

logger = get_logger("requirement_manager.mutations")

REQUIREMENT_MANAGER_AGENT_ID = "requirement-manager"


@dataclass
class RequirementMutationResult:
    """Requirement mutation result with post-commit side effects."""

    entity: Requirement | OpenQuestion | None
    event: Event | None = None
    requirement_id: str | None = None
    delete_vector_requirement_id: str | None = None


class RequirementMutationSideEffectPublisher(Protocol):
    """Port for external side effects that must run after local commit."""

    async def publish_requirement_mutation_side_effects(
        self,
        result: RequirementMutationResult,
    ) -> None:
        """Publish post-commit mutation side effects."""


class RequirementMutationWorkflow:
    """Application workflow for Requirement lifecycle mutations."""

    def __init__(
        self,
        consistency_policy: RequirementAggregateConsistencyPolicy | None = None,
    ) -> None:
        self._consistency_policy = (
            consistency_policy or RequirementAggregateConsistencyPolicy()
        )

    async def confirm_requirement(
        self,
        *,
        requirement_id: RequirementId,
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Confirm one requirement inside an explicit unit of work."""
        self._requirement_lifecycle_scope().assert_allows_same_transaction(
            (REQUIREMENT, REQUIREMENT_EVENT_OUTBOX)
        )
        requirement = await uow.requirements.confirm(requirement_id, confirmed_by)
        if not requirement:
            return RequirementMutationResult(entity=None)

        logger.info(
            "requirement_confirmed",
            requirement_id=str(requirement_id),
            confirmed_by=confirmed_by,
        )

        event = create_requirement_confirmed_event(requirement, confirmed_by)
        await uow.outbox.stage(event)
        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
        )

    async def reject_requirement(
        self,
        *,
        requirement_id: RequirementId,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Reject one requirement inside an explicit unit of work."""
        self._requirement_lifecycle_scope(
            records_feedback=True,
        ).assert_allows_same_transaction(
            (REQUIREMENT, FEEDBACK_RECORD, REQUIREMENT_EVENT_OUTBOX)
        )
        original_req = await uow.requirements.get_by_id(requirement_id)
        if not original_req:
            return RequirementMutationResult(entity=None)

        original_values = _requirement_feedback_values(original_req)
        requirement = await uow.requirements.reject(
            requirement_id,
            reason=reason,
            rejected_by=rejected_by,
        )

        if not requirement:
            return RequirementMutationResult(entity=None)

        logger.info(
            "requirement_rejected",
            requirement_id=str(requirement_id),
            reason_length=len(reason or ""),
            rejected_by_hash=hash_identifier(rejected_by),
        )

        try:
            feedback_service = FeedbackLearningService(feedback_store=uow.feedback)
            await feedback_service.record_rejection(
                requirement_id=requirement_id,
                original=original_values,
                rejected_by=rejected_by,
                reason=reason,
            )
        except Exception as exc:
            logger.warning(
                "feedback_recording_failed",
                requirement_id=str(requirement_id),
                error=str(exc),
            )

        event = create_requirement_rejected_event(requirement, reason)
        await uow.outbox.stage(event)
        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
        )

    async def update_requirement(
        self,
        *,
        requirement_id: RequirementId,
        changes: dict[str, Any],
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Update one requirement inside an explicit unit of work."""
        requirement = await uow.requirements.get_by_id(requirement_id)
        if not requirement:
            return RequirementMutationResult(entity=None)

        update_data = dict(changes)
        comment = update_data.pop("comment", None)
        if not update_data:
            return RequirementMutationResult(entity=requirement)

        original_values = _requirement_feedback_values(requirement)
        changed_fields = list(update_data.keys())
        changed_by = comment or "system"

        feedback_fields = {"title", "description", "priority", "category"}
        records_feedback = bool(update_data.keys() & feedback_fields)
        self._requirement_lifecycle_scope(
            records_feedback=records_feedback,
        ).assert_allows_same_transaction(
            (
                (REQUIREMENT, FEEDBACK_RECORD, REQUIREMENT_EVENT_OUTBOX)
                if records_feedback
                else (REQUIREMENT, REQUIREMENT_EVENT_OUTBOX)
            )
        )

        record_updated(requirement, changed_fields, changed_by)
        requirement = await uow.requirements.update(requirement_id, **update_data)
        if requirement is None:
            return RequirementMutationResult(entity=None)

        if update_data.keys() & feedback_fields:
            try:
                corrected_values = _requirement_feedback_values(requirement)
                feedback_service = FeedbackLearningService(feedback_store=uow.feedback)
                await feedback_service.record_correction(
                    requirement_id=requirement_id,
                    original=original_values,
                    corrected=corrected_values,
                    corrected_by=comment or "user",
                    note=f"Updated fields: {changed_fields}",
                )
            except Exception as exc:
                logger.warning(
                    "feedback_recording_failed",
                    requirement_id=str(requirement_id),
                    error=str(exc),
                )

        event = create_requirement_changed_event(
            requirement,
            changed_fields,
            changed_by,
        )
        await uow.outbox.stage(event)
        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
        )

    async def delete_requirement(
        self,
        *,
        requirement_id: RequirementId,
        deleted_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Delete one requirement inside an explicit unit of work."""
        self._requirement_lifecycle_scope().assert_allows_same_transaction(
            (REQUIREMENT, REQUIREMENT_EVENT_OUTBOX)
        )
        requirement = await uow.requirements.delete(requirement_id)
        if not requirement:
            return RequirementMutationResult(entity=None)

        event = create_requirement_deleted_event(requirement, deleted_by)
        await uow.outbox.stage(event)

        logger.info(
            "requirement_deleted",
            requirement_id=str(requirement_id),
            title_hash=hash_identifier(requirement.title),
            deleted_by_hash=hash_identifier(deleted_by),
        )

        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
            delete_vector_requirement_id=str(requirement_id),
        )

    async def answer_question(
        self,
        question_id: OpenQuestionId,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Answer one open clarification question inside an explicit unit of work."""
        self._consistency_policy.question_answer().assert_allows_same_transaction(
            (OPEN_QUESTION,)
        )
        question = await uow.questions.answer(
            question_id,
            answer=answer,
            answered_by=answered_by,
        )
        if not question:
            return RequirementMutationResult(entity=None)

        logger.info(
            "question_answered",
            question_id=str(question_id),
            answered_by_hash=hash_identifier(answered_by),
        )

        return RequirementMutationResult(entity=question)

    async def batch_confirm_requirements(
        self,
        *,
        requirement_ids: list[RequirementId],
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        """Confirm requirements in one explicit unit of work."""
        results = []
        mutation_results: list[RequirementMutationResult] = []

        for req_id in requirement_ids:
            try:
                result = await self.confirm_requirement(
                    requirement_id=req_id,
                    confirmed_by=confirmed_by,
                    uow=uow,
                )
                if result.entity:
                    mutation_results.append(result)
                    results.append(
                        {
                            "requirement_id": str(req_id),
                            "success": True,
                            "error": None,
                        }
                    )
                    logger.info(
                        "batch_requirement_confirmed",
                        requirement_id=str(req_id),
                        confirmed_by=confirmed_by,
                    )
                else:
                    results.append(
                        {
                            "requirement_id": str(req_id),
                            "success": False,
                            "error": "需求不存在或已处理",
                        }
                    )
            except Exception as exc:
                results.append(
                    {
                        "requirement_id": str(req_id),
                        "success": False,
                        "error": str(exc),
                    }
                )
                logger.error(
                    "batch_confirm_error",
                    requirement_id=str(req_id),
                    error=str(exc),
                )

        return results, mutation_results

    def _requirement_lifecycle_scope(
        self,
        *,
        records_feedback: bool = False,
    ):
        return self._consistency_policy.requirement_lifecycle_mutation(
            records_feedback=records_feedback,
        )

    async def batch_reject_requirements(
        self,
        *,
        requirement_ids: list[RequirementId],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        """Reject requirements in one explicit unit of work."""
        results = []
        mutation_results: list[RequirementMutationResult] = []

        for req_id in requirement_ids:
            try:
                result = await self.reject_requirement(
                    requirement_id=req_id,
                    reason=reason,
                    rejected_by=rejected_by,
                    uow=uow,
                )
                if result.entity:
                    mutation_results.append(result)
                    results.append(
                        {
                            "requirement_id": str(req_id),
                            "success": True,
                            "error": None,
                        }
                    )
                    logger.info(
                        "batch_requirement_rejected",
                        requirement_id=str(req_id),
                        reason_length=len(reason or ""),
                        rejected_by_hash=hash_identifier(rejected_by),
                    )
                else:
                    results.append(
                        {
                            "requirement_id": str(req_id),
                            "success": False,
                            "error": "需求不存在或已处理",
                        }
                    )
            except Exception as exc:
                results.append(
                    {
                        "requirement_id": str(req_id),
                        "success": False,
                        "error": str(exc),
                    }
                )
                logger.error(
                    "batch_reject_error",
                    requirement_id=str(req_id),
                    error=str(exc),
                )

        return results, mutation_results


def create_requirement_confirmed_event(
    requirement: Requirement,
    confirmed_by: str,
) -> Event:
    """Create a requirement-confirmed integration event."""
    return Event.create(
        event_type=EventTypes.REQUIREMENT_CONFIRMED,
        source_agent=REQUIREMENT_MANAGER_AGENT_ID,
        payload={
            "requirement_id": requirement.id,
            "title": requirement.title,
            "priority": requirement.priority,
            "category": requirement.category,
            "confirmed_by": confirmed_by,
            "confirmed_at": datetime.now(UTC).isoformat(),
        },
    )


def create_requirement_rejected_event(
    requirement: Requirement,
    reason: str,
) -> Event:
    """Create a requirement-rejected integration event."""
    return Event.create(
        event_type=EventTypes.REQUIREMENT_REJECTED,
        source_agent=REQUIREMENT_MANAGER_AGENT_ID,
        payload={
            "requirement_id": requirement.id,
            "title": requirement.title,
            "reason": reason,
            "rejected_at": datetime.now(UTC).isoformat(),
        },
    )


def create_requirement_changed_event(
    requirement: Requirement,
    changed_fields: list[str],
    changed_by: str,
) -> Event:
    """Create a requirement-changed integration event."""
    return Event.create(
        event_type=EventTypes.REQUIREMENT_CHANGED,
        source_agent=REQUIREMENT_MANAGER_AGENT_ID,
        payload={
            "requirement_id": requirement.id,
            "title": requirement.title,
            "changed_fields": changed_fields,
            "changed_by": changed_by,
            "changed_at": datetime.now(UTC).isoformat(),
        },
    )


def create_requirement_deleted_event(
    requirement: Requirement,
    deleted_by: str,
) -> Event:
    """Create a requirement-deleted integration event."""
    return Event.create(
        event_type=EventTypes.REQUIREMENT_DELETED,
        source_agent=REQUIREMENT_MANAGER_AGENT_ID,
        payload={
            "requirement_id": requirement.id,
            "title": requirement.title,
            "deleted_by": deleted_by,
            "deleted_at": datetime.now(UTC).isoformat(),
        },
    )


def _requirement_feedback_values(requirement: Requirement) -> dict[str, Any]:
    return {
        "title": requirement.title,
        "description": requirement.description,
        "priority": requirement.priority,
        "category": requirement.category,
    }


__all__ = [
    "RequirementMutationResult",
    "RequirementMutationSideEffectPublisher",
    "RequirementMutationWorkflow",
    "create_requirement_changed_event",
    "create_requirement_confirmed_event",
    "create_requirement_deleted_event",
    "create_requirement_rejected_event",
]
