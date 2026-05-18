from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.api.requirements import (
    analyze_requirement,
    analyze_text,
)
from agents.requirement_manager.core.analyzer import AnalysisResult


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        suggested_category="Feature",
        category_confidence=0.8,
        suggested_priority="high",
        priority_reasons=["business critical"],
        priority_confidence=0.9,
        complexity="M",
        complexity_factors=["new workflow"],
        estimated_effort_days=3,
        dependencies=[],
        blockers=[],
        risk_level="medium",
        risk_factors=[],
        suggested_tags=["launch"],
        analyzed_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_analyze_requirement_route_delegates_to_use_case():
    use_case = AsyncMock()
    use_case.analyze_requirement = AsyncMock(return_value=_analysis_result())

    result = await analyze_requirement(
        "req_test",
        use_llm=True,
        analysis=use_case,
    )

    assert result["requirement_id"] == "req_test"
    assert result["analysis"]["suggested_priority"] == "high"
    use_case.analyze_requirement.assert_awaited_once_with(
        "req_test",
        use_llm=True,
    )


@pytest.mark.asyncio
async def test_analyze_text_route_delegates_to_use_case():
    use_case = AsyncMock()
    use_case.analyze_text = AsyncMock(return_value=_analysis_result())

    result = await analyze_text(
        title="Launch flow",
        description="Support launch flow",
        use_llm=False,
        analysis=use_case,
    )

    assert result["title"] == "Launch flow"
    assert result["analysis"]["suggested_priority"] == "high"
    use_case.analyze_text.assert_awaited_once_with(
        title="Launch flow",
        description="Support launch flow",
        use_llm=False,
    )
