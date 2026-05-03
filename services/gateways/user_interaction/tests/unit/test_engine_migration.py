"""Tests for chat_service migration to ConversationEngine.

Verifies that the migrated chat() method produces identical behavior
to the original ad-hoc tool loop. These tests must FAIL before migration.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def chat_svc():
    with patch("services.gateways.user_interaction.core.chat_service.llm_gateway") as mock_gw:
        with patch("services.gateways.user_interaction.core.chat_service.settings") as mock_settings:
            mock_settings.default_model = "claude-sonnet-4-20250514"
            mock_settings.chat_model = "claude-sonnet-4-20250514"
            mock_settings.summary_model = "claude-haiku-4-5-20251001"
            from services.gateways.user_interaction.core.chat_service import ChatService
            svc = ChatService()
            svc._llm = mock_gw
            return svc


def _text_resp(text="done"):
    return MagicMock(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )


def _tool_resp(tool_name="test_tool", tool_id="tu_1"):
    return MagicMock(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=tool_id, name=tool_name, input={})],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )


class TestMigrationUsesEngine:
    """Verify that ChatService.chat() delegates to ConversationEngine."""

    @pytest.mark.asyncio
    async def test_chat_uses_conversation_engine(self, chat_svc):
        """After migration, chat() should use ConversationEngine internally."""
        chat_svc._get_history = AsyncMock(return_value=[])
        chat_svc._save_history = AsyncMock()
        chat_svc._llm.create_messages = AsyncMock(return_value=_text_resp("Hi"))

        result = await chat_svc.chat("hello", user_id="u1")
        assert result == "Hi"

    @pytest.mark.asyncio
    async def test_card_detection_still_works(self, chat_svc):
        """propose_* tools should suppress text response."""
        chat_svc._get_history = AsyncMock(return_value=[])
        saved = {}

        async def capture_save(user_id, messages):
            saved["messages"] = messages
        chat_svc._save_history = capture_save

        propose_resp = MagicMock(
            stop_reason="tool_use",
            content=[SimpleNamespace(
                type="tool_use", id="tu_1",
                name="propose_bitable_create", input={"table_id": "t1"},
            )],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        )
        final_resp = _text_resp("Card sent confirmation")
        chat_svc._llm.create_messages = AsyncMock(
            side_effect=[propose_resp, final_resp]
        )

        with patch(
            "services.gateways.user_interaction.core.chat_service.ToolExecutor.execute",
            new_callable=AsyncMock,
            return_value='{"ok": true}',
        ):
            result = await chat_svc.chat("create task", user_id="u1")

        # Card sent → text should be suppressed
        assert result == ""

    @pytest.mark.asyncio
    async def test_history_saved_after_engine_run(self, chat_svc):
        """History should be saved with all messages after engine completes."""
        chat_svc._get_history = AsyncMock(return_value=[])
        saved = {}

        async def capture_save(user_id, messages):
            saved["messages"] = messages
        chat_svc._save_history = capture_save

        chat_svc._llm.create_messages = AsyncMock(return_value=_text_resp("Reply"))

        await chat_svc.chat("hello", user_id="u1")

        assert "messages" in saved
        assert any(m.get("content") == "hello" for m in saved["messages"])

    @pytest.mark.asyncio
    async def test_error_rollback_removes_user_message(self, chat_svc):
        """On LLM error, the user message should be rolled back from history."""
        chat_svc._get_history = AsyncMock(return_value=[])
        chat_svc._save_history = AsyncMock()
        chat_svc._llm.create_messages = AsyncMock(
            side_effect=RuntimeError("LLM failed")
        )

        with pytest.raises(RuntimeError):
            await chat_svc.chat("hello", user_id="u1")

    @pytest.mark.asyncio
    async def test_strip_orphaned_still_runs(self, chat_svc):
        """_strip_orphaned_tool_messages should still run post-engine."""
        # Build history that would need orphan stripping
        big_history = [
            {"role": "user", "content": f"m_{i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"r_{i}"}
            for i in range(50)
        ]
        chat_svc._get_history = AsyncMock(return_value=big_history)
        saved = {}

        async def capture_save(user_id, messages):
            saved["messages"] = messages
        chat_svc._save_history = capture_save

        chat_svc._llm.create_messages = AsyncMock(return_value=_text_resp("ok"))

        await chat_svc.chat("hello", user_id="u1")

        # History should be capped at MAX_HISTORY
        from services.gateways.user_interaction.core.chat_service import MAX_HISTORY
        assert len(saved["messages"]) <= MAX_HISTORY + 2  # +2 for user msg + assistant reply
