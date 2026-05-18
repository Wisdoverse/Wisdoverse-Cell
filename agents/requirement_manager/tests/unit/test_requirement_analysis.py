from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.analyzer import AnalysisResult
from agents.requirement_manager.core.requirement_analysis import (
    RequirementAnalysisUseCase,
)


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
async def test_analyze_requirement_loads_requirement_and_runs_basic_analysis():
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            title="Launch flow",
            description="Support launch flow",
            source_quote="We need launch support",
        )
    )
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock(return_value=_analysis_result())

    result = await RequirementAnalysisUseCase(
        requirement_repository=repository,
        analyzer=analyzer,
    ).analyze_requirement("req_test")

    assert result is not None
    assert result.suggested_priority == "high"
    repository.get_by_id.assert_awaited_once_with("req_test")
    analyzer.analyze.assert_awaited_once_with(
        title="Launch flow",
        description="Support launch flow",
        source_quote="We need launch support",
    )


@pytest.mark.asyncio
async def test_analyze_requirement_can_use_llm_analysis():
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            title="Launch flow",
            description="Support launch flow",
            source_quote=None,
        )
    )
    analyzer = AsyncMock()
    analyzer.analyze_with_llm = AsyncMock(return_value=_analysis_result())

    result = await RequirementAnalysisUseCase(
        requirement_repository=repository,
        analyzer=analyzer,
    ).analyze_requirement("req_test", use_llm=True)

    assert result is not None
    analyzer.analyze_with_llm.assert_awaited_once_with(
        title="Launch flow",
        description="Support launch flow",
        source_quote=None,
    )


@pytest.mark.asyncio
async def test_analyze_requirement_returns_none_when_missing():
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(return_value=None)
    analyzer = AsyncMock()

    result = await RequirementAnalysisUseCase(
        requirement_repository=repository,
        analyzer=analyzer,
    ).analyze_requirement("req_missing")

    assert result is None
    analyzer.analyze.assert_not_called()
    analyzer.analyze_with_llm.assert_not_called()
