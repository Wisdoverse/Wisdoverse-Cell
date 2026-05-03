"""
Unit Tests - DecomposeService

Tests for LLM response parsing and decomposition retry logic.
"""

import json
from unittest.mock import AsyncMock

import pytest

from agents.pjm_agent.core.config import PJMCoreConfig
from agents.pjm_agent.core.decompose import DecomposeError, DecomposeService
from agents.pjm_agent.models.schemas import WBSResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_gateway():
    return AsyncMock()


@pytest.fixture
def service(llm_gateway):
    return DecomposeService(llm_gateway=llm_gateway)


# ---------------------------------------------------------------------------
# Valid JSON data helper
# ---------------------------------------------------------------------------


def _valid_wbs_dict() -> dict:
    return {
        "summary": "Build login page",
        "subtasks": [
            {
                "subject": "Design UI",
                "estimated_days": 2,
                "priority": "high",
                "depends_on": [],
                "children": [
                    {"subject": "Create wireframe", "estimated_hours": 4},
                    {"subject": "Design mockup", "estimated_hours": 8},
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# _parse_response tests
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_valid_json(self, service):
        raw = json.dumps(_valid_wbs_dict())
        result = service._parse_response(raw)
        assert isinstance(result, WBSResult)
        assert result.summary == "Build login page"
        assert len(result.subtasks) == 1
        assert result.subtasks[0].subject == "Design UI"
        assert len(result.subtasks[0].children) == 2

    def test_code_fence_wrapped_json(self, service):
        raw = "```json\n" + json.dumps(_valid_wbs_dict()) + "\n```"
        result = service._parse_response(raw)
        assert isinstance(result, WBSResult)
        assert result.summary == "Build login page"

    def test_code_fence_without_language_tag(self, service):
        raw = "```\n" + json.dumps(_valid_wbs_dict()) + "\n```"
        result = service._parse_response(raw)
        assert isinstance(result, WBSResult)
        assert result.summary == "Build login page"

    def test_code_fence_with_surrounding_text(self, service):
        raw = "Here is the result:\n```json\n" + json.dumps(_valid_wbs_dict()) + "\n```\nDone."
        result = service._parse_response(raw)
        assert isinstance(result, WBSResult)

    def test_invalid_json_raises(self, service):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            service._parse_response("this is not json at all")

    def test_empty_string_raises(self, service):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            service._parse_response("")

    def test_missing_required_key_summary(self, service):
        data = {"subtasks": _valid_wbs_dict()["subtasks"]}
        with pytest.raises(Exception):  # Pydantic ValidationError
            service._parse_response(json.dumps(data))

    def test_missing_required_key_subtasks(self, service):
        data = {"summary": "hello"}
        with pytest.raises(Exception):  # Pydantic ValidationError (min_length=1)
            service._parse_response(json.dumps(data))

    def test_empty_subtasks_raises(self, service):
        data = {"summary": "hello", "subtasks": []}
        with pytest.raises(Exception):  # min_length=1
            service._parse_response(json.dumps(data))

    def test_subtask_missing_children_raises(self, service):
        data = {
            "summary": "hello",
            "subtasks": [{"subject": "Story", "estimated_days": 1, "children": []}],
        }
        with pytest.raises(Exception):  # children min_length=1
            service._parse_response(json.dumps(data))


# ---------------------------------------------------------------------------
# decompose() retry exhaustion
# ---------------------------------------------------------------------------


class TestDecomposeRetry:
    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_decompose_error(self, service, llm_gateway):
        """When LLM returns invalid JSON, raises DecomposeError after 2 attempts."""
        llm_gateway.complete = AsyncMock(return_value="not valid json")

        with pytest.raises(DecomposeError, match="Decomposition failed"):
            await service.decompose(
                wp_id=1,
                subject="Test",
                description="Test description",
                wp_type="Feature",
            )

        assert llm_gateway.complete.await_count == 2

    @pytest.mark.asyncio
    async def test_succeeds_on_second_attempt(self, service, llm_gateway):
        """When first attempt fails but second succeeds, returns result."""
        valid_json = json.dumps(_valid_wbs_dict())
        llm_gateway.complete = AsyncMock(side_effect=["bad json", valid_json])

        result = await service.decompose(
            wp_id=1,
            subject="Test",
            description="Test description",
            wp_type="Feature",
        )

        assert isinstance(result, WBSResult)
        assert llm_gateway.complete.await_count == 2

    @pytest.mark.asyncio
    async def test_uses_injected_decompose_model(self, llm_gateway):
        """The LLM call uses the injected core config model."""
        llm_gateway.complete = AsyncMock(return_value=json.dumps(_valid_wbs_dict()))
        service = DecomposeService(
            llm_gateway=llm_gateway,
            config=PJMCoreConfig.from_values(decompose_model="pm-model"),
        )

        await service.decompose(
            wp_id=1,
            subject="Test",
            description="Test description",
            wp_type="Feature",
        )

        assert llm_gateway.complete.await_args.kwargs["model"] == "pm-model"
