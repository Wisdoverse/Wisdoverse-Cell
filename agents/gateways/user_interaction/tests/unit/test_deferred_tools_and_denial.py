"""Tests for E3 (deferred tool loading) and E4 (denial checking) in ChatService.

TDD: These tests are written FIRST, before the implementation.

E3 tests:
- _build_tool_registry marks the correct 5 tools as deferred
- to_anthropic_schemas is used in LLM calls (not raw TOOLS)
- tool_search handling adds tools to active_deferred and validator
- tool_search result is passed back as tool_result JSON

E4 tests:
- propose_* tools are blocked when DenialTracker.is_denied returns a denial
- non-propose tools bypass denial checking
- propose_* tools proceed when DenialTracker.is_denied returns None
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFERRED_TOOL_NAMES = {
    "sync_now",
    "add_bitable_field",
    "list_card_operations",
    "search_feishu_user",
    "send_feishu_message",
}


def _make_tool_use_block(*, id: str, name: str, input: dict):
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
# Fixture: ChatService with mocked deps
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_db():
    """Stub out DB calls so ChatService.chat() doesn't hit a real database."""
    with patch(
        "agents.gateways.user_interaction.core.chat_service.db_manager",
        new=MagicMock(),
    ) as mock_db:
        mock_session = AsyncMock()
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "agents.gateways.user_interaction.core.chat_service.ConversationRepository",
        ) as mock_repo_cls:
            repo_inst = AsyncMock()
            repo_inst.get_by_user = AsyncMock(return_value=[])
            repo_inst.save = AsyncMock()
            mock_repo_cls.return_value = repo_inst
            yield


@pytest.fixture()
def chat_service():
    from agents.gateways.user_interaction.core.chat_service import ChatService
    return ChatService()


# ===========================================================================
# E3: Deferred tool loading
# ===========================================================================


class TestBuildToolRegistry:
    """_build_tool_registry should mark exactly the 5 specified tools as deferred."""

    def test_deferred_tools_match_spec(self, chat_service):
        registry = chat_service._registry
        deferred = set(registry.get_deferred())
        assert deferred == _DEFERRED_TOOL_NAMES

    def test_non_deferred_tools_present(self, chat_service):
        registry = chat_service._registry
        # list_bitable_records is NOT deferred
        tool = registry.get("list_bitable_records")
        assert tool is not None
        assert tool.meta.should_defer is False

    def test_all_tools_registered(self, chat_service):
        """Every tool from TOOLS should be in the registry."""
        from agents.gateways.user_interaction.core.tools import TOOLS
        registry = chat_service._registry
        for tool_def in TOOLS:
            assert registry.get(tool_def["name"]) is not None, (
                f"Tool '{tool_def['name']}' missing from registry"
            )


class TestToolSearchInToolLoop:
    """tool_search in the tool loop should add results to active_deferred."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_tool_search_returns_results_as_json(self, chat_service):
        """When LLM calls tool_search, results should be returned as JSON tool_result."""
        tool_search_block = _make_tool_use_block(
            id="toolu_search", name="tool_search", input={"query": "sync"},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[tool_search_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("Found the sync tool.")],
        )

        with (
            patch.object(
                chat_service._llm, "create_messages",
                new=AsyncMock(side_effect=[first_response, final_response]),
            ),
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            result = await chat_service.chat("search for sync tool", user_id="u1")

        assert result == "Found the sync tool."

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_tool_search_does_not_call_tool_executor(self, chat_service):
        """tool_search should be handled inline, not via ToolExecutor."""
        tool_search_block = _make_tool_use_block(
            id="toolu_search", name="tool_search", input={"query": "sync"},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[tool_search_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("ok")],
        )

        with (
            patch.object(
                chat_service._llm, "create_messages",
                new=AsyncMock(side_effect=[first_response, final_response]),
            ),
            patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_exec,
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            mock_exec.execute = AsyncMock()
            await chat_service.chat("search", user_id="u1")
            mock_exec.execute.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_tool_search_adds_to_validator(self, chat_service):
        """After tool_search, the found tool names should be accepted by the validator."""
        # Search returns sync_now; next call uses sync_now
        tool_search_block = _make_tool_use_block(
            id="toolu_search", name="tool_search", input={"query": "sync"},
        )
        sync_block = _make_tool_use_block(
            id="toolu_sync", name="sync_now", input={},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[tool_search_block],
        )
        second_response = _make_response(
            stop_reason="tool_use",
            content=[sync_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("synced")],
        )

        with (
            patch.object(
                chat_service._llm, "create_messages",
                new=AsyncMock(side_effect=[first_response, second_response, final_response]),
            ),
            patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_exec,
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            mock_exec.execute = AsyncMock(return_value='{"success": true}')
            result = await chat_service.chat("sync please", user_id="u1")

        # sync_now should have been executed (not rejected)
        mock_exec.execute.assert_awaited_once()
        assert result == "synced"


class TestAnthropicSchemasUsed:
    """LLM calls should use registry.to_anthropic_schemas, not raw TOOLS."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_llm_receives_tool_search_in_schemas(self, chat_service):
        """The tools passed to LLM should include 'tool_search'."""
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("hi")],
        )

        mock_create = AsyncMock(return_value=final_response)
        with patch.object(chat_service._llm, "create_messages", mock_create):
            await chat_service.chat("hello", user_id="u1")

            call_kwargs = mock_create.call_args.kwargs
            tool_names = [t["name"] for t in call_kwargs["tools"]]
            assert "tool_search" in tool_names

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_tools_kwarg_is_not_raw_tools_list(self, chat_service):
        """The tools passed should come from registry, not TOOLS directly."""
        from agents.gateways.user_interaction.core.tools import TOOLS

        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("hi")],
        )

        mock_create = AsyncMock(return_value=final_response)
        with patch.object(chat_service._llm, "create_messages", mock_create):
            await chat_service.chat("hello", user_id="u1")

            call_kwargs = mock_create.call_args.kwargs
            # TOOLS has N items, registry schemas have N + 1 (tool_search)
            assert len(call_kwargs["tools"]) == len(TOOLS) + 1


# ===========================================================================
# E4: Denial checking
# ===========================================================================


class TestDenialChecking:
    """propose_* tools should be blocked when DenialTracker returns a denial."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_propose_blocked_when_denied(self, chat_service):
        """propose_bitable_update should return error when denied."""
        propose_block = _make_tool_use_block(
            id="toolu_prop", name="propose_bitable_update",
            input={"record_id": "rec1", "fields": {"状态": "完成"}, "table_id": "tbl1"},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[propose_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("OK, will try another way.")],
        )

        denial_data = {"denied_at": "2026-04-01T10:00:00", "reason": "user rejected"}

        mock_create = AsyncMock(side_effect=[first_response, final_response])
        with (
            patch.object(chat_service._llm, "create_messages", mock_create),
            patch.object(
                chat_service._denial_tracker, "is_denied",
                new=AsyncMock(return_value=denial_data),
            ),
            patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_exec,
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            mock_exec.execute = AsyncMock()
            await chat_service.chat("update the task", user_id="u1")

            # Tool should NOT have been executed
            mock_exec.execute.assert_not_awaited()

            # Check that the denial error was sent as tool_result
            second_call = mock_create.call_args_list[1]
            messages = second_call.kwargs.get("messages") or second_call[1].get("messages")
            tool_result_msg = [
                m for m in messages
                if m["role"] == "user" and isinstance(m.get("content"), list)
            ][-1]
            results = tool_result_msg["content"]
            assert len(results) == 1
            assert results[0]["is_error"] is True
            assert "已被用户拒绝" in results[0]["content"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_propose_proceeds_when_not_denied(self, chat_service):
        """propose_bitable_create should execute normally when not denied."""
        propose_block = _make_tool_use_block(
            id="toolu_prop", name="propose_bitable_create",
            input={"fields": {"任务(动宾短语)": "test task"}},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[propose_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("")],
        )

        with (
            patch.object(
                chat_service._llm, "create_messages",
                new=AsyncMock(side_effect=[first_response, final_response]),
            ),
            patch.object(
                chat_service._denial_tracker, "is_denied",
                new=AsyncMock(return_value=None),
            ),
            patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_exec,
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            mock_exec.execute = AsyncMock(return_value='{"success": true, "card_sent": true}')
            await chat_service.chat("create task", user_id="u1")

            # Tool SHOULD have been executed
            mock_exec.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_non_propose_tool_skips_denial_check(self, chat_service):
        """Non-propose tools (e.g., list_bitable_records) should not check denial tracker."""
        list_block = _make_tool_use_block(
            id="toolu_list", name="list_bitable_records", input={},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[list_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("here are records")],
        )

        with (
            patch.object(
                chat_service._llm, "create_messages",
                new=AsyncMock(side_effect=[first_response, final_response]),
            ),
            patch.object(
                chat_service._denial_tracker, "is_denied",
                new=AsyncMock(return_value=None),
            ) as mock_denied,
            patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_exec,
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            mock_exec.execute = AsyncMock(return_value='{"records": []}')
            await chat_service.chat("show tasks", user_id="u1")

            # is_denied should NOT have been called for non-propose tool
            mock_denied.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_db")
    async def test_denial_check_extracts_action_type(self, chat_service):
        """Denial check should extract action_type from propose_bitable_<action>."""
        propose_block = _make_tool_use_block(
            id="toolu_prop", name="propose_bitable_update",
            input={"record_id": "rec1", "fields": {}, "table_id": "tbl_abc"},
        )
        first_response = _make_response(
            stop_reason="tool_use",
            content=[propose_block],
        )
        final_response = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block("ok")],
        )

        with (
            patch.object(
                chat_service._llm, "create_messages",
                new=AsyncMock(side_effect=[first_response, final_response]),
            ),
            patch.object(
                chat_service._denial_tracker, "is_denied",
                new=AsyncMock(return_value=None),
            ) as mock_denied,
            patch("agents.gateways.user_interaction.core.chat_service.ToolExecutor") as mock_exec,
            patch("agents.gateways.user_interaction.core.chat_service.audit_log"),
        ):
            mock_exec.execute = AsyncMock(return_value='{"success": true}')
            await chat_service.chat("update task", user_id="u1")

            mock_denied.assert_awaited_once_with(
                agent_id="chat-agent",
                user_id="u1",
                action_type="update",
                table_id="tbl_abc",
            )


# ===========================================================================
# E3+E4: PM persona prompt includes tool_search guidance
# ===========================================================================


class TestPMPersonaPromptToolSearch:
    """USER_ASSISTANT_PROMPT should include tool_search guidance."""

    def test_prompt_mentions_tool_search(self):
        from agents.gateways.user_interaction.core.chat_service import USER_ASSISTANT_PROMPT
        assert "tool_search" in USER_ASSISTANT_PROMPT

    def test_prompt_teaches_search_strategy_without_tool_inventory(self):
        from agents.gateways.user_interaction.core.chat_service import USER_ASSISTANT_PROMPT
        assert "不熟悉的工具用 tool_search 搜索" in USER_ASSISTANT_PROMPT
        assert "sync_now" not in USER_ASSISTANT_PROMPT
        assert "add_bitable_field" not in USER_ASSISTANT_PROMPT


# ===========================================================================
# ToolValidator includes tool_search
# ===========================================================================


class TestToolValidatorIncludesToolSearch:
    """ToolValidator should recognize tool_search as a valid tool."""

    def test_tool_search_in_validator(self, chat_service):
        """tool_search should not raise ToolValidationError."""
        from shared.infra.tool_validator import ToolValidationError
        try:
            chat_service._tool_validator.validate_tool_use(
                {"name": "tool_search", "input": {"query": "test"}},
            )
        except ToolValidationError:
            pytest.fail("ToolValidator rejected tool_search — it should be registered")
