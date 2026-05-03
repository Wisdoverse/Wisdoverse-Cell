"""Card rendering ports for Requirement Manager."""

from typing import Any, Protocol


class RequirementCardRendererPort(Protocol):
    """Port for rendering outbound Requirement Manager cards."""

    def extraction_result_card(
        self,
        *,
        requirements: list[dict[str, Any]],
        meeting_title: str,
        questions_count: int,
    ) -> dict[str, Any]:
        """Render an extraction-result notification card."""

