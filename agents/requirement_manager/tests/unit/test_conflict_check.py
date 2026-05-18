from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.comparator import (
    ComparisonResult,
    RelationType,
    RequirementComparator,
)
from agents.requirement_manager.core.conflict_check import (
    RequirementConflictCheckUseCase,
)


def _comparator(vector_search, llm=None, system_prompt_resolver=None):
    if llm is None:
        llm = AsyncMock()
        llm.complete = AsyncMock()
    if system_prompt_resolver is None:
        system_prompt_resolver = AsyncMock(return_value="resolved prompt")
    return RequirementComparator(
        vector_search=vector_search,
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
        prompt_template="{new_requirement_block}\n{similar_requirements_block}",
    )


@pytest.mark.asyncio
async def test_comparator_uses_injected_vector_search_for_new_requirement():
    vector_search = AsyncMock()
    vector_search.search = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.complete = AsyncMock()
    system_prompt_resolver = AsyncMock()
    comparator = _comparator(
        vector_search,
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    )

    result = await comparator.compare(
        new_title="Offline recording",
        new_description="Support offline recording import",
        new_category="Feature",
    )

    assert result.relation == RelationType.NEW
    vector_search.search.assert_awaited_once_with(
        query="Offline recording Support offline recording import",
        n_results=5,
        min_similarity=0.6,
    )
    llm.complete.assert_not_called()
    system_prompt_resolver.assert_not_called()


@pytest.mark.asyncio
async def test_comparator_returns_duplicate_before_llm_for_high_similarity():
    vector_search = AsyncMock()
    vector_search.search = AsyncMock(
        return_value=[
            {
                "id": "req_existing",
                "title": "Offline recording",
                "category": "Feature",
                "similarity": 0.92,
            }
        ]
    )
    llm = AsyncMock()
    llm.complete = AsyncMock()
    comparator = _comparator(vector_search, llm=llm)

    result = await comparator.compare(
        new_title="Offline recording",
        new_description="Import offline recordings",
        new_category="Feature",
    )

    assert result.relation == RelationType.DUPLICATE
    assert result.related_requirement_id == "req_existing"
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_comparator_uses_injected_llm_for_medium_similarity():
    vector_search = AsyncMock()
    vector_search.search = AsyncMock(
        return_value=[
            {
                "id": "req_existing",
                "title": "Offline import",
                "category": "Feature",
                "similarity": 0.72,
            }
        ]
    )
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value="""
        {
            "relation": "update",
            "confidence": 0.8,
            "explanation": "Refines existing offline import",
            "suggested_action": "Merge changes",
            "related_requirement_id": "req_existing"
        }
        """
    )
    system_prompt_resolver = AsyncMock(return_value="resolved prompt")
    comparator = _comparator(
        vector_search,
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    )

    result = await comparator.compare(
        new_title="Offline recording",
        new_description="Import offline recordings",
        new_category="Feature",
    )

    assert result.relation == RelationType.UPDATE
    assert result.related_requirement_id == "req_existing"
    system_prompt_resolver.assert_awaited_once_with(
        "requirement-manager",
        "You are a professional requirements analysis expert. "
        "You are skilled at identifying relationships between requirements.",
    )
    llm.complete.assert_awaited_once()
    assert llm.complete.await_args.kwargs["system_prompt"] == "resolved prompt"
    assert llm.complete.await_args.kwargs["task_type"] == "conflict_detection"


@pytest.mark.asyncio
async def test_conflict_check_use_case_delegates_to_comparator():
    comparator = AsyncMock()
    comparator.compare = AsyncMock(
        return_value=ComparisonResult(
            relation=RelationType.CONFLICT,
            confidence=0.82,
            explanation="Conflicts with existing behavior",
            suggested_action="Review manually",
            related_requirement_id="req_existing",
        )
    )
    use_case = RequirementConflictCheckUseCase(comparator=comparator)

    result = await use_case.check_conflict(
        title="Offline recording",
        description="Import offline recordings",
        category="Feature",
        exclude_ids=["req_current"],
    )

    assert result.relation == RelationType.CONFLICT
    comparator.compare.assert_awaited_once_with(
        new_title="Offline recording",
        new_description="Import offline recordings",
        new_category="Feature",
        exclude_ids=["req_current"],
    )
