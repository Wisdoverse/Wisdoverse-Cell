"""
Feedback Learning Service.

Provides functionality to:
1. Record user corrections
2. Generate examples for prompt improvement
3. Track learning effectiveness
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from shared.utils.logger import get_logger

from ..db.repository import FeedbackRepository, RequirementRepository
from ..models import FeedbackRecord

logger = get_logger("feedback_learning")


class FeedbackLearningService:
    """Service for feedback-based learning."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.feedback_repo = FeedbackRepository(session)
        self.requirement_repo = RequirementRepository(session)

    async def record_correction(
        self,
        requirement_id: str,
        original: dict,
        corrected: dict,
        corrected_by: str,
        source_text: Optional[str] = None,
        note: Optional[str] = None,
    ) -> FeedbackRecord:
        """
        Record a user correction for learning.

        Args:
            requirement_id: The requirement that was corrected
            original: Original extracted values {title, description, priority, category}
            corrected: User-corrected values
            corrected_by: User ID who made the correction
            source_text: Original source text (meeting content)
            note: Optional note explaining the correction

        Returns:
            Created FeedbackRecord
        """
        feedback = FeedbackRecord(
            id=f"fb_{ULID()}",
            requirement_id=requirement_id,
            original_title=original.get("title", ""),
            original_description=original.get("description"),
            original_priority=original.get("priority"),
            original_category=original.get("category"),
            corrected_title=corrected.get("title", ""),
            corrected_description=corrected.get("description"),
            corrected_priority=corrected.get("priority"),
            corrected_category=corrected.get("category"),
            source_text=source_text,
            feedback_type="correction",
            corrected_by=corrected_by,
            correction_note=note,
        )

        await self.feedback_repo.create(feedback)

        logger.info(
            "feedback_recorded",
            feedback_id=feedback.id,
            requirement_id=requirement_id,
            corrected_by=corrected_by,
            fields_changed=self._get_changed_fields(original, corrected),
        )

        return feedback

    async def record_rejection(
        self,
        requirement_id: str,
        original: dict,
        rejected_by: str,
        reason: str,
        source_text: Optional[str] = None,
    ) -> FeedbackRecord:
        """
        Record a requirement rejection as feedback.

        This helps the model learn what NOT to extract.
        """
        feedback = FeedbackRecord(
            id=f"fb_{ULID()}",
            requirement_id=requirement_id,
            original_title=original.get("title", ""),
            original_description=original.get("description"),
            original_priority=original.get("priority"),
            original_category=original.get("category"),
            corrected_title="[REJECTED]",
            corrected_description=reason,
            source_text=source_text,
            feedback_type="rejection",
            corrected_by=rejected_by,
            correction_note=reason,
        )

        await self.feedback_repo.create(feedback)

        logger.info(
            "rejection_feedback_recorded",
            feedback_id=feedback.id,
            requirement_id=requirement_id,
            rejected_by=rejected_by,
        )

        return feedback

    async def get_prompt_examples(self, limit: int = 5) -> list[dict]:
        """
        Get correction examples for LLM prompt enhancement.

        Returns formatted examples that can be included in the
        extraction prompt for few-shot learning.
        """
        return await self.feedback_repo.get_examples_for_prompt(limit=limit)

    async def build_learning_prompt_section(self, limit: int = 3) -> str:
        """
        Build a prompt section with learning examples.

        Returns a formatted string to append to the extraction prompt.
        """
        examples = await self.get_prompt_examples(limit=limit)

        if not examples:
            return ""

        lines = [
            "",
            "## 用户反馈示例（请参考这些修正来改进提取质量）",
            "",
        ]

        for i, ex in enumerate(examples, 1):
            lines.append(f"### 示例 {i}")
            if ex.get("source_text"):
                lines.append(f"原文片段: \"{ex['source_text'][:200]}...\"")

            orig = ex.get("original", {})
            corr = ex.get("corrected", {})

            if ex.get("feedback_type") == "rejection":
                lines.append(f"❌ 错误提取: {orig.get('title', '')}")
                lines.append(f"说明: 这不应该被提取为需求。原因: {corr.get('description', '')}")
            else:
                lines.append(f"原始提取: {orig.get('title', '')}")
                lines.append(f"用户修正: {corr.get('title', '')}")
                if orig.get("priority") != corr.get("priority"):
                    lines.append(f"优先级: {orig.get('priority')} → {corr.get('priority')}")
                if orig.get("category") != corr.get("category"):
                    lines.append(f"分类: {orig.get('category')} → {corr.get('category')}")

            lines.append("")

        return "\n".join(lines)

    async def get_learning_stats(self) -> dict:
        """Get statistics about feedback/learning."""
        counts = await self.feedback_repo.count_by_type()
        examples = await self.feedback_repo.list_recent(limit=100)

        return {
            "total_feedback": sum(counts.values()),
            "by_type": counts,
            "used_in_prompt": sum(1 for e in examples if e.used_in_prompt),
            "pending_use": sum(1 for e in examples if not e.used_in_prompt),
        }

    def _get_changed_fields(self, original: dict, corrected: dict) -> list[str]:
        """Identify which fields were changed."""
        changed = []
        for field in ["title", "description", "priority", "category"]:
            if original.get(field) != corrected.get(field):
                changed.append(field)
        return changed
