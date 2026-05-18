from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.generator import DocumentGenerator


@pytest.mark.asyncio
async def test_document_generator_uses_injected_llm_and_prompt_resolver():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="```markdown\n# PRD\n```")
    system_prompt_resolver = AsyncMock(return_value="resolved prompt")
    generator = DocumentGenerator(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
        prd_prompt_template=(
            "{project_metadata_block}\n"
            "{requirements_block}\n"
        ),
    )

    result = await generator.generate_prd(
        requirements=[
            {
                "id": "req_1",
                "title": "Launch sequencing",
                "description": "Choose launch market.",
                "category": "Feature",
                "priority": "high",
                "status": "confirmed",
            }
        ],
        project_name="Wisdoverse Cell",
        version="2.0",
    )

    assert result.content == "# PRD"
    system_prompt_resolver.assert_awaited_once_with(
        "requirement-manager",
        "You are a professional technical documentation expert specialized in "
        "product requirements documents.",
    )
    llm.complete.assert_awaited_once()
    assert llm.complete.await_args.kwargs["system_prompt"] == "resolved prompt"
    assert llm.complete.await_args.kwargs["task_type"] == "document_generation"


@pytest.mark.asyncio
async def test_document_generator_skips_llm_for_empty_prd():
    llm = AsyncMock()
    llm.complete = AsyncMock()
    system_prompt_resolver = AsyncMock()
    generator = DocumentGenerator(
        llm=llm,
        system_prompt_resolver=system_prompt_resolver,
        prd_prompt_template="{project_metadata_block}\n{requirements_block}",
    )

    result = await generator.generate_prd(requirements=[])

    assert result.requirements_count == 0
    llm.complete.assert_not_called()
    system_prompt_resolver.assert_not_called()
