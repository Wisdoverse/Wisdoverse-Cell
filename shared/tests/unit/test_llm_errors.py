"""
LLM Error Taxonomy — Unit Tests

Tests for error classification, retry strategies, and ContentSizeError.
Written test-first per TDD: these tests must FAIL before llm_errors.py exists.
"""
from unittest.mock import Mock

import anthropic

from shared.infra.llm_errors import (
    ContentSizeError,
    LLMErrorCategory,
    RetryStrategy,
    classify_error,
    default_retry_config,
)


class TestLLMErrorCategory:
    """Error category enum values."""

    def test_has_all_categories(self):
        assert LLMErrorCategory.RATE_LIMIT
        assert LLMErrorCategory.OVERLOADED
        assert LLMErrorCategory.NETWORK
        assert LLMErrorCategory.AUTH
        assert LLMErrorCategory.CONTENT_SIZE
        assert LLMErrorCategory.OTHER

    def test_categories_are_strings(self):
        assert LLMErrorCategory.RATE_LIMIT.value == "rate_limit"
        assert LLMErrorCategory.OVERLOADED.value == "overloaded"
        assert LLMErrorCategory.CONTENT_SIZE.value == "content_size"


class TestClassifyError:
    """classify_error() maps Anthropic SDK exceptions to categories."""

    def test_rate_limit_error(self):
        exc = anthropic.RateLimitError(
            "Rate limited",
            response=Mock(status_code=429),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.RATE_LIMIT

    def test_overloaded_529(self):
        exc = anthropic.APIStatusError(
            "Overloaded",
            response=Mock(status_code=529),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.OVERLOADED

    def test_overloaded_503(self):
        exc = anthropic.APIStatusError(
            "Service unavailable",
            response=Mock(status_code=503),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.OVERLOADED

    def test_network_connection_error(self):
        exc = anthropic.APIConnectionError(request=Mock())
        assert classify_error(exc) == LLMErrorCategory.NETWORK

    def test_auth_error_401(self):
        exc = anthropic.AuthenticationError(
            "Unauthorized",
            response=Mock(status_code=401),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.AUTH

    def test_auth_error_403(self):
        exc = anthropic.PermissionDeniedError(
            "Forbidden",
            response=Mock(status_code=403),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.AUTH

    def test_content_size_prompt_too_long(self):
        """Anthropic returns HTTP 400 (BadRequestError) for prompt-too-long."""
        exc = anthropic.BadRequestError(
            "prompt is too long: 210000 tokens > 200000 maximum",
            response=Mock(status_code=400),
            body={"error": {"type": "invalid_request_error", "message": "prompt is too long"}},
        )
        assert classify_error(exc) == LLMErrorCategory.CONTENT_SIZE

    def test_content_size_context_length(self):
        """Alternative prompt-too-long message format."""
        exc = anthropic.BadRequestError(
            "context length exceeded",
            response=Mock(status_code=400),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.CONTENT_SIZE

    def test_bad_request_not_content_size(self):
        """400 errors that are NOT prompt-too-long should be OTHER."""
        exc = anthropic.BadRequestError(
            "invalid model",
            response=Mock(status_code=400),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.OTHER

    def test_internal_server_error_500(self):
        exc = anthropic.InternalServerError(
            "Internal error",
            response=Mock(status_code=500),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.OVERLOADED

    def test_unknown_exception_is_other(self):
        exc = RuntimeError("Something unexpected")
        assert classify_error(exc) == LLMErrorCategory.OTHER

    def test_api_status_error_502(self):
        exc = anthropic.APIStatusError(
            "Bad gateway",
            response=Mock(status_code=502),
            body={},
        )
        assert classify_error(exc) == LLMErrorCategory.OVERLOADED


class TestContentSizeError:
    """ContentSizeError wraps the original API error for ReactiveCompact."""

    def test_is_exception(self):
        err = ContentSizeError("prompt too long")
        assert isinstance(err, Exception)

    def test_not_api_status_error(self):
        """ContentSizeError should NOT inherit from APIStatusError (P0 finding)."""
        err = ContentSizeError("prompt too long")
        assert not isinstance(err, anthropic.APIStatusError)

    def test_preserves_original_via_cause(self):
        original = anthropic.BadRequestError(
            "prompt is too long",
            response=Mock(status_code=400),
            body={},
        )
        err = ContentSizeError("prompt too long")
        err.__cause__ = original
        assert err.__cause__ is original

    def test_str_representation(self):
        err = ContentSizeError("prompt is too long: 210000 > 200000")
        assert "210000" in str(err)


class TestRetryStrategy:
    """RetryStrategy dataclass holds per-category retry parameters."""

    def test_default_values(self):
        strategy = RetryStrategy()
        assert strategy.max_attempts >= 1
        assert strategy.base_delay_s > 0
        assert strategy.max_delay_s >= strategy.base_delay_s
        assert isinstance(strategy.use_jitter, bool)
        assert strategy.fallback_model is None

    def test_custom_values(self):
        strategy = RetryStrategy(
            max_attempts=6,
            base_delay_s=2.0,
            max_delay_s=60.0,
            use_jitter=True,
            fallback_model="claude-haiku-4-5-20251001",
        )
        assert strategy.max_attempts == 6
        assert strategy.fallback_model == "claude-haiku-4-5-20251001"


class TestLLMRetryConfig:
    """LLMRetryConfig holds per-category strategies."""

    def test_has_strategy_for_every_category(self):
        config = default_retry_config()
        for category in LLMErrorCategory:
            assert category in config.strategies, f"Missing strategy for {category}"

    def test_auth_no_retry(self):
        config = default_retry_config()
        assert config.strategies[LLMErrorCategory.AUTH].max_attempts == 1

    def test_content_size_no_retry(self):
        config = default_retry_config()
        assert config.strategies[LLMErrorCategory.CONTENT_SIZE].max_attempts == 1

    def test_rate_limit_multiple_retries(self):
        config = default_retry_config()
        assert config.strategies[LLMErrorCategory.RATE_LIMIT].max_attempts >= 4

    def test_overloaded_has_fallback_model(self):
        config = default_retry_config()
        strategy = config.strategies[LLMErrorCategory.OVERLOADED]
        assert strategy.fallback_model is not None

    def test_network_matches_existing_behavior(self):
        """Default network strategy must match current tenacity: 4 total attempts, 1-10s backoff."""
        config = default_retry_config()
        strategy = config.strategies[LLMErrorCategory.NETWORK]
        assert strategy.max_attempts == 4
        assert strategy.base_delay_s == 1.0
        assert strategy.max_delay_s == 10.0

    def test_persistent_mode_default_false(self):
        config = default_retry_config()
        assert config.persistent_mode is False

    def test_persistent_mode_configurable(self):
        config = default_retry_config(persistent_mode=True)
        assert config.persistent_mode is True
