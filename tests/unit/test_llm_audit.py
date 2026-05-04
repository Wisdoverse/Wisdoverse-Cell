"""Tests for audit_log integration in LLM Gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.infra.audit_log import AuditAction
from shared.infra.llm_gateway import LLMGateway
from tests.helpers.provider_errors import anthropic_like as anthropic


@pytest.fixture
def gateway():
    return LLMGateway(api_key="test-key")


def _make_mock_response(input_tokens=100, output_tokens=50):
    """Create a mock Anthropic Message response."""
    resp = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.content = [MagicMock(text="hello")]
    return resp


class TestCreateMessagesEmitsAudit:
    @pytest.mark.asyncio
    async def test_create_messages_emits_llm_call_audit(self, gateway):
        mock_resp = _make_mock_response(input_tokens=200, output_tokens=80)

        with (
            patch.object(
                gateway.async_client.messages, "create", new_callable=AsyncMock, return_value=mock_resp
            ),
            patch.object(gateway, "_get_redis", new_callable=AsyncMock, return_value=None),
            patch("shared.infra.llm_gateway.audit_log") as mock_audit,
        ):
            await gateway.create_messages(
                agent_id="test-agent",
                messages=[{"role": "user", "content": "hi"}],
                trace_id="trace-123",
            )

            mock_audit.assert_called_once()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["action"] == AuditAction.LLM_CALL
            assert call_kwargs["agent_id"] == "test-agent"
            assert call_kwargs["trace_id"] == "trace-123"
            assert call_kwargs["detail"]["input_tokens"] == 200
            assert call_kwargs["detail"]["output_tokens"] == 80
            assert "model" in call_kwargs["detail"]
            assert "cost_usd" in call_kwargs["detail"]


class TestCostCapExceededEmitsAudit:
    def test_cost_cap_exceeded_emits_audit(self, gateway):
        with patch("shared.infra.llm_gateway.audit_log") as mock_audit:
            with pytest.raises(ValueError, match="estimated_cost_exceeds_cap"):
                gateway.preflight_cost_check(
                    max_tokens=100_000,
                    model="claude-opus-4-6",
                    estimated_input_tokens=500_000,
                    cost_cap_usd=2.0,
                )

            mock_audit.assert_called_once()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["action"] == AuditAction.COST_CAP_EXCEEDED
            assert call_kwargs["agent_id"] == "system"
            assert "estimated_cost" in call_kwargs["detail"]
            assert call_kwargs["detail"]["cost_cap"] == 2.0


class TestFailedLLMCallNoAudit:
    @pytest.mark.asyncio
    async def test_failed_llm_call_no_audit(self, gateway):
        with (
            patch.object(
                gateway.async_client.messages,
                "create",
                new_callable=AsyncMock,
                side_effect=anthropic.APIError(
                    message="bad request",
                    request=MagicMock(),
                    body=None,
                ),
            ),
            patch.object(gateway, "_get_redis", new_callable=AsyncMock, return_value=None),
            patch("shared.infra.llm_gateway.audit_log") as mock_audit,
        ):
            with pytest.raises(anthropic.APIError):
                await gateway.create_messages(
                    agent_id="test-agent",
                    messages=[{"role": "user", "content": "hi"}],
                    trace_id="trace-456",
                )

            mock_audit.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_failure_logs_safe_provider_error(self, gateway):
        raw_secret = "SECRET_PROMPT_FRAGMENT user@example.com"
        persist_callback = MagicMock()

        with (
            patch.object(
                gateway.async_client.messages,
                "create",
                new_callable=AsyncMock,
                side_effect=anthropic.APIError(
                    message=f"provider rejected prompt: {raw_secret}",
                    request=MagicMock(),
                    body=None,
                ),
            ),
            patch("shared.infra.llm_gateway.logger") as mock_logger,
        ):
            with pytest.raises(anthropic.APIError):
                await gateway.complete(
                    prompt=f"Please process {raw_secret}",
                    agent_id="test-agent",
                    task_type="test",
                    persist_callback=persist_callback,
                    trace_id="trace-safe-error",
                )

        error_kwargs = mock_logger.error.call_args.kwargs
        assert "error" not in error_kwargs
        assert error_kwargs["error_category"] == "other"
        assert error_kwargs["error_type"] == "APIError"
        assert "error_fingerprint" in error_kwargs
        assert raw_secret not in str(error_kwargs)

        usage_data = persist_callback.call_args.args[0]
        assert usage_data.success is False
        assert usage_data.error_message.startswith("other:APIError:sha256:")
        assert raw_secret not in usage_data.error_message
