from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.analyzer import RequirementAnalyzer


def _analyzer(llm=None, system_prompt_resolver=None) -> RequirementAnalyzer:
    if llm is None:
        llm = AsyncMock()
        llm.complete = AsyncMock()
    if system_prompt_resolver is None:
        system_prompt_resolver = AsyncMock(return_value="resolved prompt")
    return RequirementAnalyzer(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    )


@pytest.mark.asyncio
async def test_requirement_analyzer_basic_analysis_does_not_call_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock()
    system_prompt_resolver = AsyncMock()

    result = await _analyzer(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    ).analyze(
        title="Critical API security work",
        description="Must add security validation for API access.",
    )

    assert result.suggested_priority == "high"
    assert "security" in result.suggested_tags
    llm.complete.assert_not_called()
    system_prompt_resolver.assert_not_called()


@pytest.mark.asyncio
async def test_requirement_analyzer_uses_injected_llm_and_prompt_resolver():
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value="""
        {
            "category": "security",
            "priority": "high",
            "priority_reasons": ["customer data"],
            "complexity": "M",
            "complexity_factors": ["new policy"],
            "dependencies": ["auth"],
            "risk_factors": ["PII"],
            "tags": ["security"]
        }
        """
    )
    system_prompt_resolver = AsyncMock(return_value="resolved prompt")

    result = await _analyzer(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    ).analyze_with_llm(
        title="Protect customer data",
        description="Add security validation.",
        source_quote="Customer data must be protected.",
    )

    assert result.suggested_category == "安全"
    assert result.dependencies == ["auth"]
    system_prompt_resolver.assert_awaited_once_with(
        "requirement-manager",
        "You are a requirements analysis expert. You are skilled at evaluating "
        "priority, complexity, dependencies, and risk.",
    )
    llm.complete.assert_awaited_once()
    assert llm.complete.await_args.kwargs["system_prompt"] == "resolved prompt"
    assert llm.complete.await_args.kwargs["task_type"] == "analysis"


@pytest.mark.asyncio
async def test_requirement_analyzer_falls_back_to_basic_analysis_on_llm_error():
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("llm unavailable"))
    system_prompt_resolver = AsyncMock(return_value="resolved prompt")

    result = await _analyzer(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    ).analyze_with_llm(
        title="Simple UI tweak",
        description="Adjust UI label.",
    )

    assert result.suggested_category == "UI"
    assert result.complexity == "S"
