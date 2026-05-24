"""Compatibility import for the Requirement feedback-learning service."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.domain.feedback_learning import RequirementFeedbackLearningPolicy
from ..core.feedback_learning import FeedbackLearningService as CoreFeedbackLearningService
from ..core.feedback_ports import RequirementFeedbackStore
from ..db.feedback_store import SqlAlchemyRequirementFeedbackStore


class FeedbackLearningService(CoreFeedbackLearningService):
    """Backward-compatible adapter for callers that still pass a DB session."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        feedback_store: RequirementFeedbackStore | None = None,
        feedback_policy: RequirementFeedbackLearningPolicy | None = None,
    ):
        if feedback_store is None:
            if session is None:
                raise ValueError("session or feedback_store is required")
            feedback_store = SqlAlchemyRequirementFeedbackStore(session)
        super().__init__(feedback_store=feedback_store, feedback_policy=feedback_policy)


__all__ = ["FeedbackLearningService"]
