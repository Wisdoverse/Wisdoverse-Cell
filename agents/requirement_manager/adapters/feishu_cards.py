"""Feishu card renderer adapter for Requirement Manager."""

from typing import Any

from agents.requirement_manager.core.card_ports import RequirementCardRendererPort
from agents.requirement_manager.integrations.feishu.cards.requirement import (
    build_requirement_extracted_card,
)


class FeishuRequirementCardRenderer(RequirementCardRendererPort):
    """Render Requirement Manager cards using the Feishu card schema."""

    def extraction_result_card(
        self,
        *,
        requirements: list[dict[str, Any]],
        meeting_title: str,
        questions_count: int,
    ) -> dict[str, Any]:
        return build_requirement_extracted_card(
            requirements=requirements,
            meeting_title=meeting_title,
            questions_count=questions_count,
        )

