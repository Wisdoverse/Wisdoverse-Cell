"""
LLM Error Taxonomy — Categorized errors with per-category retry strategies.

Inspired by Claude Code v2.1.88 withRetry.ts error classification.
Replaces flat retry logic with category-aware recovery.
"""
import re
from dataclasses import dataclass, field
from enum import Enum


class LLMErrorCategory(Enum):
    """Error categories for LLM API calls."""
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    NETWORK = "network"
    AUTH = "auth"
    CONTENT_SIZE = "content_size"
    OTHER = "other"


# Patterns that indicate prompt-too-long or context-window exhaustion.
_CONTENT_SIZE_PATTERNS = re.compile(
    r"prompt is too long|context length exceeded|"
    r"prompt.+tokens.+maximum|"
    r"too many tokens",
    re.IGNORECASE,
)

_OVERLOADED_STATUS_CODES = {500, 502, 503, 529}


def classify_error(exc: BaseException) -> LLMErrorCategory:
    """Map an exception to an LLMErrorCategory."""
    class_name = type(exc).__name__
    response = getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)

    if class_name == "RateLimitError" or status_code == 429:
        return LLMErrorCategory.RATE_LIMIT
    if class_name in {"AuthenticationError", "PermissionDeniedError"}:
        return LLMErrorCategory.AUTH
    if class_name in {"APIConnectionError", "APITimeoutError"}:
        return LLMErrorCategory.NETWORK
    if class_name == "BadRequestError" or status_code == 400:
        if _CONTENT_SIZE_PATTERNS.search(str(exc)):
            return LLMErrorCategory.CONTENT_SIZE
        return LLMErrorCategory.OTHER
    if isinstance(status_code, int) and status_code in _OVERLOADED_STATUS_CODES:
        return LLMErrorCategory.OVERLOADED
    if _CONTENT_SIZE_PATTERNS.search(str(exc)):
        return LLMErrorCategory.CONTENT_SIZE

    return LLMErrorCategory.OTHER


class ContentSizeError(Exception):
    """Raised when the prompt exceeds the model's context window.

    Not a provider-SDK subclass, so callers do not depend on SDK-specific
    exception constructor signatures.
    Callers that need the original error can access __cause__.
    """
    pass


@dataclass(frozen=True)
class RetryStrategy:
    """Per-category retry parameters."""
    max_attempts: int = 4
    base_delay_s: float = 1.0
    max_delay_s: float = 10.0
    use_jitter: bool = True
    fallback_model: str | None = None


@dataclass
class LLMRetryConfig:
    """Holds per-category retry strategies + persistent mode flag."""
    strategies: dict[LLMErrorCategory, RetryStrategy] = field(default_factory=dict)
    persistent_mode: bool = False
    max_persistent_seconds: float = 1800.0  # 30 minutes total cap


def default_retry_config(*, persistent_mode: bool = False) -> LLMRetryConfig:
    """Create config with sensible defaults matching existing tenacity behavior."""
    return LLMRetryConfig(
        strategies={
            LLMErrorCategory.RATE_LIMIT: RetryStrategy(
                max_attempts=6, base_delay_s=2.0, max_delay_s=60.0,
            ),
            LLMErrorCategory.OVERLOADED: RetryStrategy(
                max_attempts=3, base_delay_s=5.0, max_delay_s=30.0,
                fallback_model="claude-haiku-4-5-20251001",
            ),
            LLMErrorCategory.NETWORK: RetryStrategy(
                max_attempts=4, base_delay_s=1.0, max_delay_s=10.0,
            ),
            LLMErrorCategory.AUTH: RetryStrategy(max_attempts=1),
            LLMErrorCategory.CONTENT_SIZE: RetryStrategy(max_attempts=1),
            LLMErrorCategory.OTHER: RetryStrategy(max_attempts=1),
        },
        persistent_mode=persistent_mode,
    )
