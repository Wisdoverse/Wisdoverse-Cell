"""
_call_with_recovery — Custom retry loop replacing tenacity.

Tests for per-category retry, model fallback, persistent mode,
circuit breaker interaction, and ContentSizeError signaling.

Written test-first per TDD.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from shared.infra.llm_errors import (
    ContentSizeError,
)
from shared.infra.llm_gateway import LLMGateway
from tests.helpers.provider_errors import anthropic_like as anthropic


class MockResponse:
    """Mock Anthropic API response."""

    def __init__(self, text="OK", input_tokens=10, output_tokens=20):
        self.content = [Mock(text=text)]
        self.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)
        self.stop_reason = "end_turn"


@pytest.fixture(autouse=True)
def fast_retry_backoff():
    """Keep retry-policy unit tests deterministic and fast."""
    with (
        patch("shared.infra.llm_gateway.asyncio.sleep", new_callable=AsyncMock),
        patch("shared.infra.llm_gateway.random.uniform", return_value=0),
    ):
        yield


def _make_gateway(**overrides):
    """Create a gateway with patched settings."""
    with patch("shared.infra.llm_gateway.settings") as s:
        s.anthropic_api_key = "test-key"
        s.default_model = "claude-sonnet-4-20250514"
        s.chat_model = "claude-sonnet-4-20250514"
        s.anthropic_base_url = ""
        s.require_anthropic_proxy = False
        s.summary_model = "claude-haiku-4-5-20251001"
        s.llm_daily_budget_usd = 100.0
        s.llm_per_request_cost_cap_usd = 5.0
        s.redis_url = "redis://localhost:6379"
        for k, v in overrides.items():
            setattr(s, k, v)
        gw = LLMGateway(api_key="test-key")
    return gw


class TestCallWithRecoveryBasic:
    """Basic retry behavior via complete()."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(return_value=MockResponse("Hello"))

        result = await gw.complete(prompt="hi", agent_id="test")
        assert result == "Hello"
        assert gw.async_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_retries_then_succeeds(self):
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=[
                anthropic.RateLimitError("rate limited", response=Mock(status_code=429), body={}),
                anthropic.RateLimitError("rate limited", response=Mock(status_code=429), body={}),
                MockResponse("OK after retry"),
            ]
        )

        result = await gw.complete(prompt="hi", agent_id="test")
        assert result == "OK after retry"
        assert gw.async_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_exhaustion_uses_all_6_attempts(self):
        """Rate limits should honor the configured 6 total attempts."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.RateLimitError(
                "rate limited", response=Mock(status_code=429), body={}
            )
        )

        with patch("shared.infra.llm_gateway.asyncio.sleep", new_callable=AsyncMock):
            with patch("shared.infra.llm_gateway.random.uniform", return_value=0):
                with pytest.raises(anthropic.RateLimitError):
                    await gw.complete(prompt="hi", agent_id="test")

        assert gw.async_client.messages.create.call_count == 6

    @pytest.mark.asyncio
    async def test_network_error_4_total_attempts(self):
        """Network errors: 4 total attempts (1 initial + 3 retries) to match tenacity."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=Mock())
        )

        with pytest.raises(anthropic.APIConnectionError):
            await gw.complete(prompt="hi", agent_id="test")

        assert gw.async_client.messages.create.call_count == 4


class TestCallWithRecoveryErrorCategories:
    """Per-category behavior."""

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self):
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.AuthenticationError(
                "unauthorized", response=Mock(status_code=401), body={}
            )
        )

        with pytest.raises(anthropic.AuthenticationError):
            await gw.complete(prompt="hi", agent_id="test")

        assert gw.async_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_content_size_raises_content_size_error(self):
        """prompt-too-long (400 BadRequest) should raise ContentSizeError."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.BadRequestError(
                "prompt is too long: 210000 tokens > 200000 maximum",
                response=Mock(status_code=400),
                body={},
            )
        )

        with pytest.raises(ContentSizeError) as exc_info:
            await gw.complete(prompt="hi", agent_id="test")

        assert "prompt is too long" in str(exc_info.value)
        assert gw.async_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_content_size_preserves_cause(self):
        """ContentSizeError should chain the original BadRequestError as __cause__."""
        gw = _make_gateway()
        original = anthropic.BadRequestError(
            "prompt is too long",
            response=Mock(status_code=400),
            body={},
        )
        gw.async_client.messages.create = AsyncMock(side_effect=original)

        with pytest.raises(ContentSizeError) as exc_info:
            await gw.complete(prompt="hi", agent_id="test")

        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_bad_request_non_content_size_raises_original(self):
        """Non-prompt-too-long 400 errors should raise the original exception."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.BadRequestError(
                "invalid model",
                response=Mock(status_code=400),
                body={},
            )
        )

        with pytest.raises(anthropic.BadRequestError):
            await gw.complete(prompt="hi", agent_id="test")


class TestCallWithRecoveryFallback:
    """Model fallback on consecutive overloaded errors."""

    @pytest.mark.asyncio
    async def test_overloaded_triggers_fallback(self):
        """After max_attempts overloaded errors, switch to fallback model and succeed."""
        gw = _make_gateway()
        calls = []

        async def mock_create(**kwargs):
            calls.append(kwargs.get("model"))
            if len(calls) <= 3:
                raise anthropic.APIStatusError(
                    "Overloaded", response=Mock(status_code=529), body={}
                )
            return MockResponse("fallback OK")

        gw.async_client.messages.create = mock_create

        result = await gw.complete(prompt="hi", agent_id="test")
        assert result == "fallback OK"
        # First 3 calls: primary model, 4th call: fallback model
        assert calls[-1] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_fallback_also_fails_raises_original(self):
        """If fallback model also fails, raise the original exception type."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.APIStatusError(
                "Overloaded", response=Mock(status_code=529), body={}
            )
        )

        with pytest.raises(anthropic.APIStatusError):
            await gw.complete(prompt="hi", agent_id="test")


class TestCallWithRecoveryCircuitBreaker:
    """Circuit breaker interaction."""

    @pytest.mark.asyncio
    async def test_success_records_breaker_success(self):
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(return_value=MockResponse())

        await gw.complete(prompt="hi", agent_id="test")
        assert gw._circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_exhausted_retries_records_one_failure(self):
        """Circuit breaker records exactly 1 failure after all retries exhausted."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=Mock())
        )

        try:
            await gw.complete(prompt="hi", agent_id="test")
        except anthropic.APIConnectionError:
            pass

        assert gw._circuit_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_successful_fallback_records_breaker_success(self):
        """When fallback model succeeds, circuit breaker records success (not failure)."""
        gw = _make_gateway()
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise anthropic.APIStatusError(
                    "Overloaded", response=Mock(status_code=529), body={}
                )
            return MockResponse("fallback OK")

        gw.async_client.messages.create = mock_create

        await gw.complete(prompt="hi", agent_id="test")
        # Fallback succeeded → breaker should record success
        assert gw._circuit_breaker.failure_count == 0


class TestCallWithRecoveryCreateMessages:
    """Ensure create_messages() also uses the new retry loop."""

    @pytest.mark.asyncio
    async def test_create_messages_retries_on_overload(self):
        gw = _make_gateway()
        gw._redis = None  # skip Redis

        async def fake_downgrade(model):
            return model
        gw._maybe_downgrade_model = fake_downgrade

        calls = []

        async def mock_create(**kwargs):
            calls.append(kwargs.get("model"))
            if len(calls) <= 2:
                raise anthropic.APIStatusError(
                    "Overloaded", response=Mock(status_code=529), body={}
                )
            return MockResponse("OK")

        gw.async_client.messages.create = mock_create

        response = await gw.create_messages(
            agent_id="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert response.content[0].text == "OK"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_create_messages_content_size_error(self):
        """create_messages() should raise ContentSizeError for prompt-too-long."""
        gw = _make_gateway()
        gw._redis = None

        async def fake_downgrade(model):
            return model
        gw._maybe_downgrade_model = fake_downgrade

        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.BadRequestError(
                "prompt is too long",
                response=Mock(status_code=400),
                body={},
            )
        )

        with pytest.raises(ContentSizeError):
            await gw.create_messages(
                agent_id="test",
                messages=[{"role": "user", "content": "x" * 100000}],
            )

    @pytest.mark.asyncio
    async def test_create_messages_tracks_actual_fallback_model(self):
        """Usage and cost accounting should use the fallback model that actually answered."""
        gw = _make_gateway()

        async def fake_downgrade(model):
            return model

        gw._maybe_downgrade_model = fake_downgrade
        gw._track_usage = Mock()
        gw._track_redis_cost = AsyncMock()

        calls = []

        async def mock_create(**kwargs):
            calls.append(kwargs.get("model"))
            if len(calls) <= 3:
                raise anthropic.APIStatusError(
                    "Overloaded", response=Mock(status_code=529), body={}
                )
            return MockResponse("fallback OK")

        gw.async_client.messages.create = mock_create

        with patch.object(gw, "estimate_cost", return_value=0.123) as estimate_cost:
            with patch("shared.infra.llm_gateway.asyncio.sleep", new_callable=AsyncMock):
                with patch("shared.infra.llm_gateway.random.uniform", return_value=0):
                    response = await gw.create_messages(
                        agent_id="test",
                        model="claude-sonnet-4-20250514",
                        messages=[{"role": "user", "content": "hi"}],
                    )

        assert response.content[0].text == "fallback OK"
        assert calls[-1] == "claude-haiku-4-5-20251001"
        assert estimate_cost.call_args_list[-1].args == (
            10, 20, "claude-haiku-4-5-20251001"
        )
        assert gw._track_usage.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"


class TestPersistentModeTimeCap:
    """Persistent mode must have a total time cap to prevent infinite loops."""

    @pytest.mark.asyncio
    async def test_persistent_mode_respects_total_time_cap(self):
        """persistent_mode should give up after max_persistent_seconds."""
        from shared.infra.llm_errors import default_retry_config

        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.RateLimitError(
                "rate limited", response=Mock(status_code=429), body={}
            )
        )

        config = default_retry_config(persistent_mode=True)
        config.max_persistent_seconds = 0  # Zero = immediately exhausted

        with patch("shared.infra.llm_gateway.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(anthropic.RateLimitError):
                await gw._call_with_recovery(
                    {"model": "test", "max_tokens": 100, "messages": [{"role": "user", "content": "hi"}]},
                    retry_config=config,
                )

    @pytest.mark.asyncio
    async def test_persistent_mode_does_not_retry_auth(self):
        """persistent_mode should NOT retry auth errors."""
        from shared.infra.llm_errors import default_retry_config

        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.AuthenticationError(
                "bad key", response=Mock(status_code=401), body={}
            )
        )

        config = default_retry_config(persistent_mode=True)

        with pytest.raises(anthropic.AuthenticationError):
            await gw._call_with_recovery(
                {"model": "test", "max_tokens": 100, "messages": [{"role": "user", "content": "hi"}]},
                retry_config=config,
            )

        assert gw.async_client.messages.create.call_count == 1


class TestAgentIdMetric:
    """agent_id label should propagate to error metrics."""

    @pytest.mark.asyncio
    async def test_agent_id_passed_to_call_with_recovery(self):
        """_call_with_recovery should accept agent_id and use it for metrics."""
        gw = _make_gateway()
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.APIConnectionError(request=Mock())
            return MockResponse("OK")

        gw.async_client.messages.create = mock_create

        result = await gw._call_with_recovery(
            {"model": "test", "max_tokens": 100, "messages": [{"role": "user", "content": "hi"}]},
            agent_id="chat-agent",
        )
        assert result.content[0].text == "OK"


class TestPersistCallbackErrorPath:
    """persist_callback error path must log, not silently swallow."""

    @pytest.mark.asyncio
    async def test_error_path_persist_callback_logged(self):
        """When complete() fails AND persist_callback raises, the callback error should be logged."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=Mock())
        )

        callback = Mock(side_effect=RuntimeError("DB down"))

        import shared.infra.llm_gateway as gw_mod
        original_logger = gw_mod.logger

        logged = []
        class CapLogger:
            def __getattr__(self, name):
                def log_method(*args, **kwargs):
                    logged.append({"level": name, "args": args, "kwargs": kwargs})
                    getattr(original_logger, name)(*args, **kwargs)
                return log_method

        gw_mod.logger = CapLogger()
        try:
            with pytest.raises(anthropic.APIConnectionError):
                await gw.complete(prompt="hi", agent_id="test", persist_callback=callback)

            persist_warnings = [
                entry for entry in logged
                if entry["level"] == "warning"
                and "persist" in str(entry["args"])
            ]
            assert len(persist_warnings) >= 1, "persist_callback failure in error path must be logged"
        finally:
            gw_mod.logger = original_logger


class TestCallWithRecoveryExceptionPreservation:
    """Custom loop must re-raise original exception types (not wrappers)."""

    @pytest.mark.asyncio
    async def test_rate_limit_raises_rate_limit_error(self):
        """After exhausting retries, the original RateLimitError is raised (not RetryError)."""
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.RateLimitError(
                "Rate limited", response=Mock(status_code=429), body={}
            )
        )

        with pytest.raises(anthropic.RateLimitError):
            await gw.complete(prompt="hi", agent_id="test")

    @pytest.mark.asyncio
    async def test_internal_error_raises_internal_server_error(self):
        gw = _make_gateway()
        gw.async_client.messages.create = AsyncMock(
            side_effect=anthropic.InternalServerError(
                "Server error", response=Mock(status_code=500), body={}
            )
        )

        with pytest.raises(anthropic.InternalServerError):
            await gw.complete(prompt="hi", agent_id="test")
