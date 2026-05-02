"""Tests for ToolValidator wiring in ChatService tool-calling loop."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.gateways.user_interaction.core.chat_service import ChatService
from shared.infra.audit_log import AuditAction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_use_block(*, id: str, name: str, input: dict):
    """Create a SimpleNamespace mimicking a Claude content block."""
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _make_text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _make_response(*, stop_reason: str, content: list):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chat_service():
    svc = ChatService()
    return svc


@pytest.fixture()
def _patch_db():
    """Stub out DB calls so ChatService.chat() doesn't hit a real database."""
    with (
        patch(
            "agents.gateways.user_interaction.core.chat_service.db_manager",
            new=MagicMock(),
        ) as mock_db,
    ):
        # Make the async context manager return a mock session
        mock_session = AsyncMock()
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
        # ConversationRepository stubs
        with patch(
            "agents.gateways.user_interaction.core.chat_service.ConversationRepository",
        ) as mock_repo_cls:
            repo_inst = AsyncMock()
            repo_inst.get_by_user = AsyncMock(return_value=[])
            repo_inst.save = AsyncMock()
            mock_repo_cls.return_value = repo_inst
            yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_db")
async def test_known_tool_passes_validation(chat_service):
    """A known tool with valid input should execute normally and emit success audit."""
    tool_block = _make_tool_use_block(
        id="toolu_1", name="get_work_packages", input={"limit": 5},
    )
    # First LLM call returns tool_use, second returns text (end of loop)
    first_response = _make_response(
        stop_reason="tool_use",
        content=[tool_block],
    )
    final_response = _make_response(
        stop_reason="end_turn",
        content=[_make_text_block("Here are the results.")],
    )

    with (
        patch.object(chat_service._llm, "create_messages", new=AsyncMock(side_effect=[first_response, final_response])),
        patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_executor_cls,
        patch("agents.gateways.user_interaction.core.chat_service.audit_log") as mock_audit,
    ):
        mock_executor_cls.execute = AsyncMock(return_value='{"work_packages": []}')

        result = await chat_service.chat("show tasks", user_id="u1")

        assert result == "Here are the results."
        mock_executor_cls.execute.assert_awaited_once()
        # Successful execution should emit audit with success=True
        mock_audit.assert_any_call(
            action=AuditAction.TOOL_EXECUTED,
            agent_id="chat-agent",
            detail={"tool": "get_work_packages", "success": True},
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_db")
async def test_unknown_tool_rejected_and_audited(chat_service):
    """An unknown tool should be rejected, audit-logged, and an error result returned."""
    bad_block = _make_tool_use_block(
        id="toolu_bad", name="hack_the_planet", input={},
    )
    first_response = _make_response(
        stop_reason="tool_use",
        content=[bad_block],
    )
    final_response = _make_response(
        stop_reason="end_turn",
        content=[_make_text_block("Sorry, that tool is not available.")],
    )

    with (
        patch.object(chat_service._llm, "create_messages", new=AsyncMock(side_effect=[first_response, final_response])),
        patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_executor_cls,
        patch("agents.gateways.user_interaction.core.chat_service.audit_log") as mock_audit,
    ):
        mock_executor_cls.execute = AsyncMock()

        await chat_service.chat("do bad thing", user_id="u1")

        # Tool should NOT have been executed
        mock_executor_cls.execute.assert_not_awaited()
        # Audit should log the rejection
        mock_audit.assert_any_call(
            action=AuditAction.TOOL_EXECUTED,
            agent_id="chat-agent",
            detail={"tool": "hack_the_planet", "rejected": True, "reason": "unknown_tool: Tool 'hack_the_planet' is not registered"},
        )
        # The LLM should have received an error tool_result (check history passed to second LLM call)
        second_call_args = chat_service._llm.create_messages.call_args_list[1]
        messages = second_call_args.kwargs.get("messages") or second_call_args[1].get("messages")
        # Find the user message with tool_results
        tool_result_msg = [m for m in messages if m["role"] == "user" and isinstance(m.get("content"), list)][-1]
        results = tool_result_msg["content"]
        assert len(results) == 1
        assert results[0]["tool_use_id"] == "toolu_bad"
        assert results[0]["is_error"] is True
        assert "unknown_tool" in results[0]["content"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_db")
async def test_oversized_tool_input_rejected(chat_service):
    """Tool input exceeding the size limit should be rejected and audited."""
    # Create input larger than 100KB
    huge_input = {"data": "x" * 200_000}
    big_block = _make_tool_use_block(
        id="toolu_big", name="get_work_packages", input=huge_input,
    )
    first_response = _make_response(
        stop_reason="tool_use",
        content=[big_block],
    )
    final_response = _make_response(
        stop_reason="end_turn",
        content=[_make_text_block("Input was too large.")],
    )

    with (
        patch.object(chat_service._llm, "create_messages", new=AsyncMock(side_effect=[first_response, final_response])),
        patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_executor_cls,
        patch("agents.gateways.user_interaction.core.chat_service.audit_log") as mock_audit,
    ):
        mock_executor_cls.execute = AsyncMock()

        await chat_service.chat("big input", user_id="u1")

        mock_executor_cls.execute.assert_not_awaited()
        # Check audit logged with rejected=True and reason containing "too_large"
        audit_calls = [c for c in mock_audit.call_args_list if c.kwargs.get("detail", {}).get("rejected")]
        assert len(audit_calls) == 1
        assert "too_large" in audit_calls[0].kwargs["detail"]["reason"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_patch_db")
async def test_multiple_tool_use_blocks_validated_independently(chat_service):
    """Each tool_use block should be validated independently; one bad block doesn't block others."""
    good_block = _make_tool_use_block(
        id="toolu_ok", name="sync_now", input={},
    )
    bad_block = _make_tool_use_block(
        id="toolu_bad", name="evil_tool", input={},
    )
    first_response = _make_response(
        stop_reason="tool_use",
        content=[good_block, bad_block],
    )
    final_response = _make_response(
        stop_reason="end_turn",
        content=[_make_text_block("Done.")],
    )

    with (
        patch.object(chat_service._llm, "create_messages", new=AsyncMock(side_effect=[first_response, final_response])),
        patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_executor_cls,
        patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
    ):
        mock_executor_cls.execute = AsyncMock(return_value='{"success": true}')

        await chat_service.chat("do things", user_id="u1")

        # Good tool should execute, bad tool should not
        mock_executor_cls.execute.assert_awaited_once_with(
            "sync_now", {}, context=None,
        )
        # Check tool_results sent to LLM: should have 2 results
        second_call_args = chat_service._llm.create_messages.call_args_list[1]
        messages = second_call_args.kwargs.get("messages") or second_call_args[1].get("messages")
        tool_result_msg = [m for m in messages if m["role"] == "user" and isinstance(m.get("content"), list)][-1]
        results = tool_result_msg["content"]
        assert len(results) == 2
        # One success, one error
        ok_result = next(r for r in results if r["tool_use_id"] == "toolu_ok")
        err_result = next(r for r in results if r["tool_use_id"] == "toolu_bad")
        assert "is_error" not in ok_result or ok_result.get("is_error") is not True
        assert err_result["is_error"] is True
