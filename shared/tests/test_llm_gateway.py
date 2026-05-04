"""
LLM Gateway unit tests.

Coverage:
1. Retry mechanism with exponential backoff
2. Circuit breaker integration
3. Retryable and non-retryable errors
4. Cost tracking
"""
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from shared.infra.circuit_breaker import CircuitBreakerError, CircuitState
from shared.infra.llm_gateway import RETRYABLE_STATUS_CODES, LLMGateway
from tests.helpers.provider_errors import anthropic_like as anthropic

APIStatusError = anthropic.APIStatusError
RateLimitError = anthropic.RateLimitError


class MockResponse:
    """Mock Anthropic API response."""

    def __init__(self, text: str = "Test response", input_tokens: int = 10, output_tokens: int = 20):
        self.content = [Mock(text=text)]
        self.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)


class TestLLMGatewayBasic:
    """Basic behavior tests."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway for tests."""
        with patch('shared.infra.llm_gateway.settings') as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.default_model = "claude-sonnet-4-20250514"
            mock_settings.chat_model = "claude-sonnet-4-20250514"
            mock_settings.anthropic_base_url = ""
            mock_settings.require_anthropic_proxy = False
            mock_settings.llm_daily_budget_usd = 100.0
            mock_settings.llm_per_request_cost_cap_usd = 5.0
            mock_settings.control_plane_llm_budget_enforced = False
            mock_settings.redis_url = "redis://localhost:6379"
            gateway = LLMGateway(api_key="test-key")
            yield gateway

    @pytest.mark.asyncio
    async def test_successful_call(self, gateway):
        """Successful call returns the response."""
        gateway.async_client.messages.create = AsyncMock(return_value=MockResponse("Hello"))

        result = await gateway.complete(
            prompt="Test prompt",
            agent_id="test-agent"
        )

        assert result == "Hello"
        gateway.async_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_tracks_usage(self, gateway):
        """Usage is tracked."""
        gateway.async_client.messages.create = AsyncMock(
            return_value=MockResponse(input_tokens=100, output_tokens=50)
        )

        await gateway.complete(prompt="Test", agent_id="test-agent")

        usage = gateway.get_usage_today("test-agent")
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["calls"] == 1

    @pytest.mark.asyncio
    async def test_complete_redacts_sensitive_prompt_values(self, gateway):
        """Provider payloads must not receive raw secrets or direct PII."""
        gateway.async_client.messages.create = AsyncMock(return_value=MockResponse("OK"))

        await gateway.complete(
            prompt=(
                "Contact user@example.com or +1 (415) 555-0199. "
                "OpenID ou_1234567890abcdef. "
                "See https://example.feishu.cn/docx/abc?token=secret-value "
                "with api_key=sk-1234567890abcdefghijklmnop."
            ),
            agent_id="test-agent",
            system_prompt="Authorization: Bearer eyJabc.def.ghi",
        )

        payload = json.dumps(
            gateway.async_client.messages.create.call_args.kwargs,
            ensure_ascii=False,
        )
        assert "user@example.com" not in payload
        assert "+1 (415) 555-0199" not in payload
        assert "ou_1234567890abcdef" not in payload
        assert "secret-value" not in payload
        assert "sk-1234567890abcdefghijklmnop" not in payload
        assert "eyJabc.def.ghi" not in payload
        assert "[REDACTED_EMAIL]" in payload
        assert "[REDACTED_PHONE]" in payload
        assert "[REDACTED_PLATFORM_ID]" in payload
        assert "[REDACTED_SECRET]" in payload

    def test_estimate_cost(self, gateway):
        """Cost is estimated correctly."""
        # claude-sonnet-4: $3/M input, $15/M output
        cost = gateway.estimate_cost(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="claude-sonnet-4-20250514"
        )

        assert cost == 18.0  # $3 + $15

    @pytest.mark.asyncio
    async def test_create_messages_redacts_nested_sensitive_values(self, gateway):
        """Conversation-history payloads are sanitized before provider calls."""
        gateway.async_client.messages.create = AsyncMock(return_value=MockResponse("OK"))

        with patch.object(gateway, "_get_redis", new_callable=AsyncMock, return_value=None):
            await gateway.create_messages(
                agent_id="test-agent",
                system=[{"type": "text", "text": "client_secret=raw-secret"}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Email admin@example.com and phone 13800138000. "
                                    "Use Authorization: Bearer ghp_1234567890abcdefghij"
                                ),
                            }
                        ],
                    }
                ],
            )

        payload = json.dumps(
            gateway.async_client.messages.create.call_args.kwargs,
            ensure_ascii=False,
        )
        assert "raw-secret" not in payload
        assert "admin@example.com" not in payload
        assert "13800138000" not in payload
        assert "ghp_1234567890abcdefghij" not in payload
        assert "[REDACTED_SECRET]" in payload
        assert "[REDACTED_EMAIL]" in payload
        assert "[REDACTED_PHONE]" in payload


class TestLLMGatewayRetry:
    """Retry behavior tests."""

    @pytest.fixture
    def gateway(self):
        mock_logger = MagicMock()
        with patch('shared.infra.llm_gateway.settings') as mock_settings, \
             patch('shared.infra.llm_gateway.logger', mock_logger):
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.default_model = "claude-sonnet-4-20250514"
            mock_settings.anthropic_base_url = ""
            mock_settings.require_anthropic_proxy = False
            gateway = LLMGateway(api_key="test-key")
            yield gateway

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, gateway):
        """429 errors are retried."""
        # First two calls fail, third call succeeds.
        gateway.async_client.messages.create = AsyncMock(
            side_effect=[
                RateLimitError("Rate limited", response=Mock(status_code=429), body={}),
                RateLimitError("Rate limited", response=Mock(status_code=429), body={}),
                MockResponse("Success after retry")
            ]
        )

        result = await gateway.complete(prompt="Test", agent_id="test-agent")

        assert result == "Success after retry"
        assert gateway.async_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_500_error(self, gateway):
        """500 errors are retried."""
        error_response = Mock(status_code=500)
        gateway.async_client.messages.create = AsyncMock(
            side_effect=[
                anthropic.InternalServerError("Server error", response=error_response, body={}),
                MockResponse("Success")
            ]
        )

        result = await gateway.complete(prompt="Test", agent_id="test-agent")

        assert result == "Success"
        assert gateway.async_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_400_error(self, gateway):
        """400 errors are not retried."""
        error_response = Mock(status_code=400)
        gateway.async_client.messages.create = AsyncMock(
            side_effect=APIStatusError(
                "Bad request",
                response=error_response,
                body={}
            )
        )

        with pytest.raises(APIStatusError):
            await gateway.complete(prompt="Test", agent_id="test-agent")

        # Called once with no retry.
        assert gateway.async_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, gateway):
        """Exceeding max retries raises the original error."""
        gateway.async_client.messages.create = AsyncMock(
            side_effect=RateLimitError(
                "Rate limited",
                response=Mock(status_code=429),
                body={}
            )
        )

        with patch("shared.infra.llm_gateway.asyncio.sleep", new_callable=AsyncMock), \
             patch("shared.infra.llm_gateway.random.uniform", return_value=0):
            with pytest.raises(RateLimitError):
                await gateway.complete(prompt="Test", agent_id="test-agent")

        # rate_limit classification defaults to 6 total attempts.
        assert gateway.async_client.messages.create.call_count == 6


class TestLLMGatewayCircuitBreaker:
    """Circuit breaker integration tests."""

    @pytest.fixture
    def gateway(self):
        mock_logger = MagicMock()
        with patch('shared.infra.llm_gateway.settings') as mock_settings, \
             patch('shared.infra.llm_gateway.logger', mock_logger):
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.default_model = "claude-sonnet-4-20250514"
            mock_settings.anthropic_base_url = ""
            mock_settings.require_anthropic_proxy = False
            # Low threshold for tests.
            gateway = LLMGateway(
                api_key="test-key",
                failure_threshold=2,
                recovery_timeout=60
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, gateway):
        """Circuit opens after repeated failures."""
        # Use InternalServerError instead of APIConnectionError because the
        # latter has changed constructor signatures across SDK versions.
        error_response = Mock(status_code=500)
        gateway.async_client.messages.create = AsyncMock(
            side_effect=anthropic.InternalServerError("Server error", response=error_response, body={})
        )

        # Trigger failures. Each call retries internally.
        for _ in range(2):
            try:
                await gateway.complete(prompt="Test", agent_id="test-agent")
            except Exception:
                pass

        # Circuit should be open.
        stats = gateway.get_circuit_breaker_stats()
        assert stats["state"] == "open"

    @pytest.mark.asyncio
    async def test_rejects_when_circuit_open(self, gateway):
        """Open circuit rejects requests."""
        error_response = Mock(status_code=500)
        gateway.async_client.messages.create = AsyncMock(
            side_effect=anthropic.InternalServerError("Server error", response=error_response, body={})
        )

        # Trigger open circuit.
        for _ in range(2):
            try:
                await gateway.complete(prompt="Test", agent_id="test-agent")
            except Exception:
                pass

        # Subsequent request should be rejected.
        with pytest.raises(CircuitBreakerError):
            await gateway.complete(prompt="Test", agent_id="test-agent")

    @pytest.mark.asyncio
    async def test_circuit_closes_on_success(self, gateway):
        """Circuit closes after success."""
        gateway.async_client.messages.create = AsyncMock(return_value=MockResponse("Success"))

        await gateway.complete(prompt="Test", agent_id="test-agent")

        stats = gateway.get_circuit_breaker_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0

    def test_reset_circuit_breaker(self, gateway):
        """Circuit breaker can be reset manually."""
        # Simulate open circuit.
        gateway._circuit_breaker._state = CircuitState.OPEN
        gateway._circuit_breaker._failure_count = 5

        gateway.reset_circuit_breaker()

        stats = gateway.get_circuit_breaker_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0


class TestRetryableStatusCodes:
    """Retryable status code tests."""

    def test_retryable_codes(self):
        """Validate retryable status codes."""
        assert 429 in RETRYABLE_STATUS_CODES  # Rate limit
        assert 500 in RETRYABLE_STATUS_CODES  # Internal server error
        assert 502 in RETRYABLE_STATUS_CODES  # Bad gateway
        assert 503 in RETRYABLE_STATUS_CODES  # Service unavailable
        assert 529 in RETRYABLE_STATUS_CODES  # Overloaded

    def test_non_retryable_codes(self):
        """Validate non-retryable status codes."""
        assert 400 not in RETRYABLE_STATUS_CODES  # Bad request
        assert 401 not in RETRYABLE_STATUS_CODES  # Unauthorized
        assert 403 not in RETRYABLE_STATUS_CODES  # Forbidden
        assert 404 not in RETRYABLE_STATUS_CODES  # Not found
