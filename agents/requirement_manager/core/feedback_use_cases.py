"""Application use cases for requirement feedback workflows."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BatchOperationSummary:
    """Summary for batch requirement feedback operations."""

    total: int
    succeeded: int
    failed: int
    results: list[dict]


class RequirementFeedbackAgent(Protocol):
    async def confirm_requirement(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        session: object,
    ) -> object | None:
        """Confirm one requirement."""

    async def reject_requirement(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        session: object,
    ) -> object | None:
        """Reject one requirement."""

    async def answer_question(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        session: object,
    ) -> object | None:
        """Answer one open question."""

    async def list_open_questions(self, *, session: object) -> list[object]:
        """List open questions."""

    async def batch_confirm_requirements(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
    ) -> list[dict]:
        """Confirm multiple requirements."""

    async def batch_reject_requirements(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> list[dict]:
        """Reject multiple requirements."""


class RequirementFeedbackUseCase:
    """Application use case for requirement feedback operations."""

    def __init__(self, *, agent: RequirementFeedbackAgent, session: object):
        self._agent = agent
        self._session = session

    async def confirm_requirement(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
    ) -> object | None:
        return await self._agent.confirm_requirement(
            requirement_id=requirement_id,
            confirmed_by=confirmed_by,
            session=self._session,
        )

    async def reject_requirement(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
    ) -> object | None:
        return await self._agent.reject_requirement(
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by,
            session=self._session,
        )

    async def answer_question(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
    ) -> object | None:
        return await self._agent.answer_question(
            question_id,
            answer=answer,
            answered_by=answered_by,
            session=self._session,
        )

    async def list_open_questions(self) -> list[object]:
        return await self._agent.list_open_questions(session=self._session)

    async def batch_confirm_requirements(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
    ) -> BatchOperationSummary:
        results = await self._agent.batch_confirm_requirements(
            requirement_ids=requirement_ids,
            confirmed_by=confirmed_by,
        )
        return _summarize_batch(results)

    async def batch_reject_requirements(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> BatchOperationSummary:
        results = await self._agent.batch_reject_requirements(
            requirement_ids=requirement_ids,
            reason=reason,
            rejected_by=rejected_by,
        )
        return _summarize_batch(results)


def _summarize_batch(results: list[dict]) -> BatchOperationSummary:
    succeeded = sum(1 for result in results if result["success"])
    failed = len(results) - succeeded
    return BatchOperationSummary(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )
