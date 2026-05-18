from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.extractor import RequirementExtractor


def _extractor(llm=None, system_prompt_resolver=None) -> RequirementExtractor:
    if llm is None:
        llm = AsyncMock()
        llm.complete = AsyncMock()
    if system_prompt_resolver is None:
        system_prompt_resolver = AsyncMock(return_value="resolved prompt")
    return RequirementExtractor(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
        prompt_template="{meeting_notes_block}\n{context_block}",
    )


@pytest.mark.asyncio
async def test_requirement_extractor_uses_injected_llm_and_prompt_resolver():
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value="""
        {
            "requirements": [
                {
                    "title": "Offline recording",
                    "description": "Import offline recordings.",
                    "category": "feature",
                    "priority": "high",
                    "source_quote": "Need offline recording."
                }
            ],
            "decisions": [{"content": "Ship MVP", "decided_by": "PM"}],
            "open_questions": [{"question": "Which file format?", "context": "Import"}]
        }
        """
    )
    system_prompt_resolver = AsyncMock(return_value="resolved prompt")

    result = await _extractor(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
    ).extract(
        content="Need offline recording.",
        source="upload",
        meeting_date="2026-05-17",
        participants=["Alice"],
        context="Planning",
    )

    assert result.requirements[0].title == "Offline recording"
    assert result.requirements[0].category == "功能"
    assert result.requirements[0].priority == "high"
    assert result.decisions[0].content == "Ship MVP"
    assert result.open_questions[0].question == "Which file format?"
    system_prompt_resolver.assert_awaited_once_with(
        "requirement-manager",
        "You are a professional product requirements analyst. "
        "You are skilled at extracting structured requirements from meeting notes.",
    )
    llm.complete.assert_awaited_once()
    assert llm.complete.await_args.kwargs["system_prompt"] == "resolved prompt"
    assert llm.complete.await_args.kwargs["task_type"] == "extraction"


@pytest.mark.asyncio
async def test_requirement_extractor_returns_empty_result_for_invalid_json():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="not json")

    result = await _extractor(llm=llm).extract(content="Meeting notes.")

    assert result.requirements == []
    assert result.decisions == []
    assert result.open_questions == []
