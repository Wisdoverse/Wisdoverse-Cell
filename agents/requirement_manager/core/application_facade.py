"""Application facade for the Requirement Manager service shell."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.core import FeishuMessengerPort
from shared.schemas.event import Event

from ..models import Meeting, OpenQuestion, Requirement
from .card_ports import RequirementCardRendererPort
from .ingest_side_effect_use_cases import (
    RequirementIngestSideEffectUseCase,
    RequirementSessionExtractionCardUseCase,
)
from .meeting_ingest_workflow import IngestResult, RequirementMeetingIngestWorkflow
from .mutation_side_effect_use_cases import RequirementMutationSideEffectUseCase
from .outbox_delivery_use_cases import RequirementOutboxDeliveryUseCase
from .read_query_use_cases import RequirementReadQueryUseCase
from .requirement_command_use_cases import RequirementCommandUseCase
from .requirement_mutation_workflow import RequirementMutationResult
from .unit_of_work_ports import (
    RequirementSessionUnitOfWorkFactory,
    RequirementUnitOfWork,
    RequirementUnitOfWorkFactory,
)


class RequirementApplicationFacade:
    """Coordinate Requirement use cases behind the runtime agent boundary."""

    def __init__(
        self,
        *,
        uow_factory: RequirementUnitOfWorkFactory,
        session_uow_factory: RequirementSessionUnitOfWorkFactory,
        ingest_workflow: RequirementMeetingIngestWorkflow,
        command_use_case: RequirementCommandUseCase,
        read_query_use_case: RequirementReadQueryUseCase,
        mutation_side_effects: RequirementMutationSideEffectUseCase,
        ingest_side_effects: RequirementIngestSideEffectUseCase,
        outbox_delivery: RequirementOutboxDeliveryUseCase,
        messenger: FeishuMessengerPort | None = None,
        card_renderer: RequirementCardRendererPort | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._session_uow_factory = session_uow_factory
        self._ingest_workflow = ingest_workflow
        self._command_use_case = command_use_case
        self._read_query_use_case = read_query_use_case
        self._mutation_side_effects = mutation_side_effects
        self._ingest_side_effects = ingest_side_effects
        self._outbox_delivery = outbox_delivery
        self._messenger = messenger
        self._card_renderer = card_renderer

    def configure_messenger(self, messenger: FeishuMessengerPort | None) -> None:
        """Wire the outbound messaging adapter used by application workflows."""
        self._messenger = messenger

    def configure_card_renderer(
        self,
        card_renderer: RequirementCardRendererPort | None,
    ) -> None:
        """Wire the outbound card renderer used by application workflows."""
        self._card_renderer = card_renderer

    def get_unit_of_work(self):
        """Open one transaction-scoped Requirement unit of work."""
        return self._uow_factory()

    def session_unit_of_work(self, session: object) -> RequirementUnitOfWork:
        """Adapt a caller-owned legacy session to the Requirement UOW boundary."""
        return self._session_uow_factory(session)

    async def ingest_meeting(
        self,
        content: str,
        source: str,
        session: object | None = None,
        title: str | None = None,
        meeting_date: datetime | None = None,
        participants: list[str] | None = None,
        context: str | None = None,
        source_id: str | None = None,
    ) -> IngestResult:
        """Ingest meeting content and publish post-commit side effects."""
        if session is not None:
            uow = self.session_unit_of_work(session)
            result = await self.ingest_meeting_with_uow(
                content=content,
                source=source,
                uow=uow,
                title=title,
                meeting_date=meeting_date,
                participants=participants,
                context=context,
                source_id=source_id,
            )
            await uow.commit()
        else:
            async with self._uow_factory() as uow:
                result = await self.ingest_meeting_with_uow(
                    content=content,
                    source=source,
                    uow=uow,
                    title=title,
                    meeting_date=meeting_date,
                    participants=participants,
                    context=context,
                    source_id=source_id,
                )
                await uow.commit()

        await self.publish_ingest_side_effects(result)
        return result

    async def ingest_meeting_with_uow(
        self,
        *,
        content: str,
        source: str,
        uow: RequirementUnitOfWork,
        title: str | None = None,
        meeting_date: datetime | None = None,
        participants: list[str] | None = None,
        context: str | None = None,
        source_id: str | None = None,
    ) -> IngestResult:
        """Ingest meeting content inside an explicit Requirement unit of work."""
        return await self._ingest_workflow.ingest_meeting(
            content=content,
            source=source,
            uow=uow,
            title=title,
            meeting_date=meeting_date,
            participants=participants,
            context=context,
            source_id=source_id,
        )

    async def publish_ingest_side_effects(self, result: IngestResult) -> None:
        """Publish integration and notification side effects after ingest commit."""
        await self._ingest_side_effects.publish_ingest_side_effects(result)

    async def confirm_requirement(
        self,
        requirement_id: str,
        confirmed_by: str,
        session: object | None = None,
    ) -> Requirement | None:
        if session is not None:
            return await self._command_use_case.confirm_requirement(
                requirement_id=requirement_id,
                confirmed_by=confirmed_by,
                uow=self.session_unit_of_work(session),
            )
        return await self._command_use_case.confirm_requirement(
            requirement_id=requirement_id,
            confirmed_by=confirmed_by,
        )

    async def confirm_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._command_use_case.confirm_requirement_with_uow(
            requirement_id=requirement_id,
            confirmed_by=confirmed_by,
            uow=uow,
        )

    async def reject_requirement(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        session: object | None = None,
    ) -> Requirement | None:
        if session is not None:
            return await self._command_use_case.reject_requirement(
                requirement_id=requirement_id,
                reason=reason,
                rejected_by=rejected_by,
                uow=self.session_unit_of_work(session),
            )
        return await self._command_use_case.reject_requirement(
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by,
        )

    async def reject_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._command_use_case.reject_requirement_with_uow(
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by,
            uow=uow,
        )

    async def update_requirement(
        self,
        requirement_id: str,
        changes: dict[str, Any],
        session: object | None = None,
    ) -> Requirement | None:
        if session is not None:
            return await self._command_use_case.update_requirement(
                requirement_id=requirement_id,
                changes=changes,
                uow=self.session_unit_of_work(session),
            )
        return await self._command_use_case.update_requirement(
            requirement_id=requirement_id,
            changes=changes,
        )

    async def update_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        changes: dict[str, Any],
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._command_use_case.update_requirement_with_uow(
            requirement_id=requirement_id,
            changes=changes,
            uow=uow,
        )

    async def delete_requirement(
        self,
        requirement_id: str,
        deleted_by: str,
        session: object | None = None,
    ) -> Requirement | None:
        if session is not None:
            return await self._command_use_case.delete_requirement(
                requirement_id=requirement_id,
                deleted_by=deleted_by,
                uow=self.session_unit_of_work(session),
            )
        return await self._command_use_case.delete_requirement(
            requirement_id=requirement_id,
            deleted_by=deleted_by,
        )

    async def delete_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._command_use_case.delete_requirement_with_uow(
            requirement_id=requirement_id,
            deleted_by=deleted_by,
            uow=uow,
        )

    async def answer_question(
        self,
        question_id: str,
        answer: str,
        answered_by: str,
        session: object | None = None,
    ) -> OpenQuestion | None:
        if session is not None:
            return await self._command_use_case.answer_question(
                question_id,
                answer=answer,
                answered_by=answered_by,
                uow=self.session_unit_of_work(session),
            )
        return await self._command_use_case.answer_question(
            question_id,
            answer=answer,
            answered_by=answered_by,
        )

    async def answer_question_with_uow(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._command_use_case.answer_question_with_uow(
            question_id,
            answer=answer,
            answered_by=answered_by,
            uow=uow,
        )

    async def list_open_questions(
        self,
        session: object | None = None,
        *,
        limit: int = 50,
    ) -> list[OpenQuestion]:
        if session is not None:
            return await self._read_query_use_case.list_open_questions_with_uow(
                self.session_unit_of_work(session),
                limit=limit,
            )
        return await self._read_query_use_case.list_open_questions(limit=limit)

    async def publish_requirement_mutation_side_effects(
        self,
        result: RequirementMutationResult,
    ) -> None:
        await self._mutation_side_effects.publish_requirement_mutation_side_effects(
            result,
        )

    async def publish_pending_requirement_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery.publish_pending_events(limit=limit)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery.publish_event_via_outbox(event)

    async def list_pending_requirements(
        self,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict], int, int]:
        return await self._read_query_use_case.list_pending_requirements(
            page=page,
            page_size=page_size,
        )

    async def get_confirmed_requirements(self) -> list[dict]:
        return await self._read_query_use_case.get_confirmed_requirements()

    async def batch_confirm_requirements(
        self,
        requirement_ids: list[str],
        confirmed_by: str,
    ) -> list[dict]:
        return await self._command_use_case.batch_confirm_requirements(
            requirement_ids=requirement_ids,
            confirmed_by=confirmed_by,
        )

    async def batch_confirm_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        return await self._command_use_case.batch_confirm_requirements_with_uow(
            requirement_ids=requirement_ids,
            confirmed_by=confirmed_by,
            uow=uow,
        )

    async def batch_reject_requirements(
        self,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> list[dict]:
        return await self._command_use_case.batch_reject_requirements(
            requirement_ids=requirement_ids,
            reason=reason,
            rejected_by=rejected_by,
        )

    async def batch_reject_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        return await self._command_use_case.batch_reject_requirements_with_uow(
            requirement_ids=requirement_ids,
            reason=reason,
            rejected_by=rejected_by,
            uow=uow,
        )

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self._read_query_use_case.get_requirement(requirement_id)

    async def get_meeting(self, meeting_id: str) -> Meeting | None:
        return await self._read_query_use_case.get_meeting(meeting_id)

    async def send_session_extraction_card(
        self,
        chat_id: str,
        result: IngestResult,
        session_id: str,
    ) -> None:
        await self._session_card_use_case().send_session_extraction_card(
            chat_id,
            result,
            session_id,
        )

    def _session_card_use_case(self) -> RequirementSessionExtractionCardUseCase:
        return RequirementSessionExtractionCardUseCase(
            messenger=self._messenger,
            card_renderer=self._card_renderer,
        )
