"""
LLM Gateway - centralized LLM access point.

All agents access LLMs through this gateway. It provides:
1. A unified interface.
2. Cost tracking with Redis-based daily budget metering.
3. Failure retry with exponential backoff.
4. Circuit breaker protection.
5. Durable usage records.
6. Budget controls with model downgrade support.
7. LiteLLM routing for multiple model providers.
"""
import asyncio
import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Callable, Optional

from ..config import settings
from ..control_plane.context import get_current_run_context
from ..observability.privacy import hash_identifier
from ..utils.logger import get_logger
from .audit_log import AuditAction, audit_log
from .budget_events import publish_budget_usage_recorded
from .circuit_breaker import CircuitBreaker, CircuitBreakerError
from .llm_errors import (
    ContentSizeError,
    LLMErrorCategory,
    LLMRetryConfig,
    classify_error,
    default_retry_config,
)
from .metrics import (
    LLM_COST_DOLLARS_TOTAL,
    LLM_DAILY_COST_DOLLARS,
    LLM_ERROR_TOTAL,
    LLM_FALLBACK_TOTAL,
    LLM_REQUEST_DURATION,
    LLM_TOKEN_TOTAL,
)

logger = get_logger("llm_gateway")

# Redis key prefix for daily cost tracking
_REDIS_COST_KEY_PREFIX = "llm_cost"

# Retryable HTTP status codes
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


@dataclass
class LLMUsageData:
    """
    LLM call usage data.

    Passed to persistence callbacks with all relevant fields for one LLM call.
    """
    agent_id: str
    task_type: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    success: bool
    error_message: Optional[str] = None
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class ControlPlaneBudgetReservation:
    """A pre-approved durable budget bucket for one LLM call."""

    company_id: str
    budget_id: str


# Persistence callback type
UsagePersistCallback = Callable[[LLMUsageData], Any]


def _is_retryable_error(exception: BaseException) -> bool:
    """
    Return whether an exception is retryable.

    Retryable errors include:
    - Rate limits (429)
    - Provider overload/server errors (500/502/503/529)
    - Network errors
    """
    category = classify_error(exception)
    if category in {
        LLMErrorCategory.RATE_LIMIT,
        LLMErrorCategory.OVERLOADED,
        LLMErrorCategory.NETWORK,
    }:
        return True
    status_code = getattr(exception, "status_code", None)
    response = getattr(exception, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    return status_code in RETRYABLE_STATUS_CODES


class _LiteLLMMessagesClient:
    """Compatibility wrapper exposing a messages.create-style API."""

    def __init__(self, gateway: "LLMGateway"):
        self._gateway = gateway

    async def create(self, **create_kwargs: Any) -> Any:
        return await self._gateway._litellm_messages_create(create_kwargs)


class LLMGateway:
    """
    LLM call gateway.

    Features:
    - Exponential backoff retry: 1s -> 2s -> 4s, up to three retries.
    - Circuit breaker: opens after five consecutive failures, then probes after 60s.
    - Cost tracking: records token usage for each call.
    - Fully async: uses LiteLLM's OpenAI-compatible async completion API.

    LiteLLM is the only supported provider boundary. Agents must not instantiate
    provider SDK clients directly.

    Usage:
        gateway = LLMGateway()
        response = await gateway.complete(
            prompt="Extract requirements...",
            agent_id="requirement-manager",
            task_type="extraction"
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        """
        Initialize the LLM gateway.

        Args:
            api_key: Optional provider API key override for LiteLLM routes.
            base_url: Optional LiteLLM/provider proxy base URL.
            timeout: Client timeout in seconds
            failure_threshold: Circuit breaker failure threshold.
            recovery_timeout: Circuit breaker recovery timeout in seconds.
        """
        self.provider = "litellm"
        self._explicit_api_key = api_key
        self._provider_api_keys = {
            "anthropic": self._secret_setting("anthropic_api_key"),
            "openai": self._secret_setting("openai_api_key"),
            "openrouter": self._secret_setting("openrouter_api_key"),
            "gemini": self._secret_setting("gemini_api_key")
            or self._secret_setting("google_api_key"),
        }
        self.api_key = api_key or self._provider_api_keys["anthropic"]
        self.timeout = timeout
        litellm_api_base = base_url or getattr(settings, "litellm_api_base", "")
        self._litellm_api_base = (
            litellm_api_base.rstrip("/") if isinstance(litellm_api_base, str) else ""
        )

        # Compatibility surface for tests and legacy callers that patch
        # ``gateway.async_client.messages.create``. The implementation still
        # routes through LiteLLM only.
        self.async_client = SimpleNamespace(messages=_LiteLLMMessagesClient(self))

        # Circuit breaker.
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            name="llm_gateway"
        )

        # Cost tracking. This in-memory map is kept for backward compatibility.
        self._usage_today: dict[str, dict] = {}

        # Redis client for distributed cost tracking (lazy-initialized)
        self._redis = None

    @staticmethod
    def _secret_setting(name: str) -> str:
        """Read a Settings secret value without coupling to SecretStr in tests."""
        value = getattr(settings, name, "")
        if hasattr(value, "get_secret_value"):
            return value.get_secret_value()
        return str(value or "")

    def _provider_for_model(self, model: str) -> str:
        """Return the LiteLLM provider implied by a model name."""
        normalized = model.strip().lower()
        if normalized.startswith("openrouter/"):
            return "openrouter"
        if normalized.startswith(("claude-", "anthropic/")):
            return "anthropic"
        if normalized.startswith(("openai/", "azure/", "gpt-", "o1", "o3", "o4")):
            return "openai"
        if normalized.startswith(("gemini/", "google/", "vertex_ai/")):
            return "gemini"
        return "generic"

    def _api_key_for_model(self, model: str) -> str:
        """Choose the API key that matches the selected LiteLLM route."""
        if self._explicit_api_key:
            return self._explicit_api_key
        if self._litellm_api_base and self._provider_api_keys["openai"]:
            return self._provider_api_keys["openai"]
        provider = self._provider_for_model(model)
        return self._provider_api_keys.get(provider, "")

    def _normalize_litellm_model(self, model: str) -> str:
        """Map native Claude model names to LiteLLM's provider/model format."""
        if "/" in model:
            return model
        if model.startswith("claude-"):
            return f"anthropic/{model}"
        return model

    def _anthropic_model_for_cost(self, model: str) -> str:
        """Strip LiteLLM provider prefix when matching existing Claude price table."""
        if model.startswith("anthropic/"):
            return model.split("/", 1)[1]
        return model

    def _record_llm_success_metrics(
        self,
        *,
        model: str,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        """Emit Prometheus metrics for successful LLM usage."""
        LLM_REQUEST_DURATION.labels(model=model, agent_id=agent_id).observe(
            latency_ms / 1000.0
        )
        LLM_TOKEN_TOTAL.labels(
            model=model,
            agent_id=agent_id,
            token_type="input",
        ).inc(input_tokens)
        LLM_TOKEN_TOTAL.labels(
            model=model,
            agent_id=agent_id,
            token_type="output",
        ).inc(output_tokens)
        LLM_COST_DOLLARS_TOTAL.labels(model=model, agent_id=agent_id).inc(cost_usd)

    def _system_blocks_to_text(self, system: Any) -> str:
        if not system:
            return ""
        if isinstance(system, str):
            return system
        parts: list[str] = []
        for block in system:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
            else:
                text = getattr(block, "text", None) or getattr(block, "content", None)
            if text:
                parts.append(str(text))
        return "\n\n".join(parts)

    def _anthropic_content_to_openai_messages(self, role: str, content: Any) -> list[dict]:
        """Convert Anthropic-style message content into OpenAI-compatible messages."""
        if isinstance(content, str):
            return [{"role": role, "content": content}]
        if not isinstance(content, list):
            return [{"role": role, "content": str(content)}]

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_result_messages: list[dict] = []

        for block in content:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type == "text":
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                if text:
                    text_parts.append(str(text))
            elif block_type == "tool_use":
                tool_id = block.get("id") if isinstance(block, dict) else getattr(block, "id", "")
                name = block.get("name") if isinstance(block, dict) else getattr(block, "name", "")
                tool_input = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                tool_calls.append({
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(tool_input or {}, ensure_ascii=False),
                    },
                })
            elif block_type == "tool_result":
                tool_use_id = (
                    block.get("tool_use_id")
                    if isinstance(block, dict)
                    else getattr(block, "tool_use_id", "")
                )
                result_content = (
                    block.get("content")
                    if isinstance(block, dict)
                    else getattr(block, "content", "")
                )
                tool_result_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_use_id,
                    "content": result_content if isinstance(result_content, str) else str(result_content),
                })

        if tool_result_messages:
            messages = []
            if text_parts:
                messages.append({"role": role, "content": "\n".join(text_parts)})
            messages.extend(tool_result_messages)
            return messages

        message: dict[str, Any] = {"role": role, "content": "\n".join(text_parts) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return [message]

    def _messages_to_litellm(self, *, system: Any = None, messages: list[dict]) -> list[dict]:
        converted: list[dict] = []
        system_text = self._system_blocks_to_text(system)
        if system_text:
            converted.append({"role": "system", "content": system_text})
        for message in messages:
            converted.extend(
                self._anthropic_content_to_openai_messages(
                    str(message.get("role", "user")),
                    message.get("content", ""),
                )
            )
        return converted

    def _tools_to_litellm(self, tools: list[dict] | None) -> list[dict] | None:
        """Convert Anthropic tool schemas to OpenAI function tool schemas."""
        if not tools:
            return None
        converted: list[dict] = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                converted.append(tool)
                continue
            converted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return converted

    def _litellm_kwargs(self, create_kwargs: dict) -> dict:
        model = self._normalize_litellm_model(create_kwargs["model"])
        kwargs = {
            "model": model,
            "messages": self._messages_to_litellm(
                system=create_kwargs.get("system"),
                messages=create_kwargs.get("messages", []),
            ),
            "max_tokens": create_kwargs.get("max_tokens"),
            "temperature": create_kwargs.get("temperature"),
        }
        tools = self._tools_to_litellm(create_kwargs.get("tools"))
        if tools:
            kwargs["tools"] = tools
        api_base = self._litellm_api_base
        if api_base:
            kwargs["api_base"] = api_base
        api_key = self._api_key_for_model(model)
        if api_key:
            kwargs["api_key"] = api_key
        return {key: value for key, value in kwargs.items() if value is not None}

    def _response_value(self, obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _adapt_litellm_response(self, response: Any) -> Any:
        """Adapt OpenAI Chat Completion responses to the Anthropic-like shape we use."""
        choices = self._response_value(response, "choices", []) or []
        choice = choices[0] if choices else {}
        message = self._response_value(choice, "message", {}) or {}
        content_text = self._response_value(message, "content", "") or ""
        tool_calls = self._response_value(message, "tool_calls", None) or []

        content_blocks: list[Any] = []
        if content_text:
            content_blocks.append(SimpleNamespace(type="text", text=content_text))

        for tool_call in tool_calls:
            function = self._response_value(tool_call, "function", {}) or {}
            raw_arguments = self._response_value(function, "arguments", "{}") or "{}"
            try:
                parsed_arguments = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError):
                parsed_arguments = {"raw_arguments": str(raw_arguments)}
            content_blocks.append(
                SimpleNamespace(
                    type="tool_use",
                    id=self._response_value(tool_call, "id", ""),
                    name=self._response_value(function, "name", ""),
                    input=parsed_arguments,
                )
            )

        usage = self._response_value(response, "usage", None) or {}
        input_tokens = self._response_value(
            usage,
            "prompt_tokens",
            self._response_value(usage, "input_tokens", 0),
        )
        output_tokens = self._response_value(
            usage,
            "completion_tokens",
            self._response_value(usage, "output_tokens", 0),
        )
        stop_reason = "tool_use" if tool_calls else self._response_value(choice, "finish_reason", "stop")
        if stop_reason == "stop":
            stop_reason = "end_turn"

        return SimpleNamespace(
            content=content_blocks,
            usage=SimpleNamespace(
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
            ),
            stop_reason=stop_reason,
        )

    async def _litellm_messages_create(self, create_kwargs: dict) -> Any:
        try:
            from litellm import acompletion
        except ImportError as exc:
            raise RuntimeError(
                "LLMGateway requires the litellm package. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        response = await acompletion(**self._litellm_kwargs(create_kwargs))
        return self._adapt_litellm_response(response)

    async def _provider_messages_create(self, create_kwargs: dict) -> Any:
        return await self.async_client.messages.create(**create_kwargs)

    async def complete(
        self,
        prompt: str,
        agent_id: str,
        task_type: str = "general",
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0,
        system_prompt: Optional[str] = None,
        trace_id: Optional[str] = None,
        persist_callback: Optional[UsagePersistCallback] = None,
        company_id: Optional[str] = None,
        budget_scope: Optional[str] = None,
        budget_scope_id: Optional[str] = None,
        budget_period: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """
        Call the LLM to complete a task.

        Args:
            prompt: User prompt.
            agent_id: Calling agent ID for cost tracking.
            task_type: Task type (extraction/generation/analysis/conversation).
            model: Model name, defaults to the configured model.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            system_prompt: System prompt.
            trace_id: Optional trace ID for request correlation.
            persist_callback: Optional callback for persisting usage data.
            company_id: Optional control-plane company for durable budget checks.
            budget_scope: Optional budget scope override (company/goal/agent/work_item).
            budget_scope_id: Optional budget scope identifier.
            budget_period: Optional budget period override (daily/monthly/quarterly/total).
            run_id: Optional control-plane agent run ID for usage linkage.

        Returns:
            LLM response text.

        Raises:
            CircuitBreakerError: When the circuit breaker is open.
            Exception: When the provider call fails after retries are exhausted.
        """
        model = model or settings.default_model
        start_time = time.time()
        run_context = get_current_run_context()
        resolved_company_id = company_id or (
            run_context.company_id if run_context is not None else None
        )
        resolved_run_id = run_id or (run_context.run_id if run_context is not None else None)
        estimated_input_tokens = self._estimate_payload_tokens(
            {
                "system": system_prompt or "You are a helpful assistant.",
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        estimated_cost_usd = self.estimate_cost(estimated_input_tokens, max_tokens, model)
        budget_reservation = await self._check_control_plane_budget(
            company_id=resolved_company_id,
            agent_id=agent_id,
            scope=budget_scope,
            scope_id=budget_scope_id,
            period=budget_period,
            model=model,
            estimated_cost_usd=estimated_cost_usd,
            trace_id=trace_id,
        )

        # Check circuit breaker state.
        if not self._circuit_breaker.can_execute():
            logger.warning(
                "llm_call_rejected",
                agent_id=agent_id,
                reason="circuit_breaker_open"
            )
            raise CircuitBreakerError(
                f"LLM Gateway circuit breaker is open. "
                f"Will recover after {self._circuit_breaker.recovery_timeout}s."
            )

        try:
            create_kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": [{"type": "text", "text": system_prompt or "You are a helpful assistant."}],
                "messages": [{"role": "user", "content": prompt}],
            }
            response = await self._call_with_recovery(
                create_kwargs,
                agent_id=agent_id,
            )
            model = create_kwargs["model"]

            # Record success.
            self._circuit_breaker.record_success()

            # Record usage.
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            latency_ms = int((time.time() - start_time) * 1000)
            cost_usd = self.estimate_cost(input_tokens, output_tokens, model)

            self._track_usage(
                agent_id=agent_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            await self._record_control_plane_budget_usage(
                reservation=budget_reservation,
                cost_usd=cost_usd,
                model=model,
                source_agent_id=agent_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                run_id=resolved_run_id,
                trace_id=trace_id,
            )

            self._record_llm_success_metrics(
                model=model,
                agent_id=agent_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )

            logger.info(
                "llm_call_completed",
                agent_id=agent_id,
                task_type=task_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost_usd
            )

            audit_log(
                action=AuditAction.LLM_CALL,
                agent_id=agent_id,
                detail={
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": round(cost_usd, 6),
                },
                trace_id=trace_id,
            )

            # Invoke persistence callback.
            if persist_callback:
                usage_data = LLMUsageData(
                    agent_id=agent_id,
                    task_type=task_type,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    success=True,
                    trace_id=trace_id
                )
                try:
                    persist_callback(usage_data)
                except Exception as persist_error:
                    # Persistence failures must not block the main flow.
                    logger.warning(
                        "llm_usage_persist_failed",
                        error=str(persist_error)
                    )

            # Extract text response.
            text_parts = []
            for block in response.content:
                block_type = getattr(block, "type", None)
                if not isinstance(block_type, str) and hasattr(block, "text"):
                    block_type = "text"
                if block_type == "text" and getattr(block, "text", None):
                    text_parts.append(block.text)
            return "".join(text_parts)

        except ContentSizeError:
            # Content-size is not a service failure — don't trip breaker
            raise

        except Exception as e:
            # All retries+fallback exhausted — record one breaker failure
            self._circuit_breaker.record_failure()
            latency_ms = int((time.time() - start_time) * 1000)
            error_message = self._safe_provider_error_message(e)
            error_category = classify_error(e).value

            logger.error(
                "llm_call_failed",
                agent_id=agent_id,
                task_type=task_type,
                model=model,
                latency_ms=latency_ms,
                error_category=error_category,
                error_type=type(e).__name__,
                error_fingerprint=hash_identifier(str(e), length=16),
            )

            if persist_callback:
                usage_data = LLMUsageData(
                    agent_id=agent_id,
                    task_type=task_type,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=error_message,
                    trace_id=trace_id,
                )
                try:
                    persist_callback(usage_data)
                except Exception as persist_error:
                    logger.warning(
                        "llm_usage_persist_failed",
                        error=str(persist_error),
                        context="error_path",
                    )

            raise

    async def _call_with_recovery(
        self,
        create_kwargs: dict,
        retry_config: LLMRetryConfig | None = None,
        agent_id: str = "unknown",
    ) -> Any:
        """
        Category-aware retry loop replacing tenacity.

        Error categories determine retry strategy (attempts, backoff, fallback).
        ContentSizeError raised for prompt-too-long (caller handles via ReactiveCompact).
        Model fallback on consecutive overloaded errors.
        Circuit breaker interaction:
        - record_failure() called once after ALL retries+fallback exhausted
        - Successful fallback = caller records breaker success
        """
        config = retry_config or default_retry_config()
        last_exc: BaseException | None = None
        fallback_attempted = False
        start_time = time.time()

        while True:
            # Determine strategy based on last error category
            if last_exc is not None:
                category = classify_error(last_exc)
                strategy = config.strategies.get(
                    category, config.strategies[LLMErrorCategory.OTHER]
                )
            else:
                # First pass: use network strategy as default (matches old tenacity 4-attempt)
                category = None
                strategy = config.strategies[LLMErrorCategory.NETWORK]

            attempt = 0
            while attempt < strategy.max_attempts:
                attempt += 1
                try:
                    return await self._provider_messages_create(create_kwargs)
                except Exception as exc:
                    last_exc = exc
                    category = classify_error(exc)
                    strategy = config.strategies.get(
                        category, config.strategies[LLMErrorCategory.OTHER]
                    )

                    # Content size → raise ContentSizeError immediately
                    if category == LLMErrorCategory.CONTENT_SIZE:
                        raise ContentSizeError(str(exc)) from exc

                    # No-retry categories
                    if strategy.max_attempts <= 1:
                        raise

                    # Last attempt exhausted
                    if attempt >= strategy.max_attempts:
                        break

                    # Exponential backoff with jitter
                    delay = min(
                        strategy.base_delay_s * (2 ** (attempt - 1)),
                        strategy.max_delay_s,
                    )
                    if strategy.use_jitter:
                        delay += random.uniform(0, 0.25 * delay)

                    LLM_ERROR_TOTAL.labels(
                        category=category.value,
                        model=create_kwargs.get("model", "unknown"),
                        agent_id=agent_id,
                    ).inc()
                    logger.warning(
                        "llm_retry",
                        category=category.value,
                        attempt=attempt,
                        max_attempts=strategy.max_attempts,
                        delay_s=round(delay, 2),
                        model=create_kwargs.get("model"),
                    )
                    await asyncio.sleep(delay)

            # All attempts for this strategy exhausted.
            # Try fallback model if overloaded and not yet attempted.
            if (
                category == LLMErrorCategory.OVERLOADED
                and strategy.fallback_model
                and not fallback_attempted
            ):
                fallback_attempted = True
                LLM_FALLBACK_TOTAL.labels(
                    from_model=create_kwargs.get("model", "unknown"),
                    to_model=strategy.fallback_model,
                ).inc()
                logger.warning(
                    "llm_fallback",
                    from_model=create_kwargs.get("model"),
                    to_model=strategy.fallback_model,
                )
                create_kwargs["model"] = strategy.fallback_model
                last_exc = None
                continue

            # Persistent mode: keep retrying rate_limit / overloaded (with total time cap)
            if config.persistent_mode and category in (
                LLMErrorCategory.RATE_LIMIT,
                LLMErrorCategory.OVERLOADED,
            ):
                elapsed = time.time() - start_time
                if elapsed >= config.max_persistent_seconds:
                    logger.error(
                        "llm_persistent_retry_exhausted",
                        category=category.value,
                        elapsed_s=round(elapsed, 1),
                        max_s=config.max_persistent_seconds,
                        agent_id=agent_id,
                    )
                    raise last_exc
                delay = min(strategy.max_delay_s, 300)  # 5 min cap
                logger.warning(
                    "llm_persistent_retry",
                    category=category.value,
                    delay_s=delay,
                    elapsed_s=round(elapsed, 1),
                )
                await asyncio.sleep(delay)
                continue

            # All recovery exhausted — re-raise original exception
            if last_exc:
                raise last_exc
            raise RuntimeError("_call_with_recovery: unexpected state")

    async def _call_with_retry(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str],
    ):
        """LLM call with retry; delegates to _call_with_recovery."""
        return await self._call_with_recovery({
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": [{"type": "text", "text": system_prompt or "You are a helpful assistant."}],
            "messages": [{"role": "user", "content": prompt}],
        })

    async def create_messages(
        self,
        *,
        agent_id: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0,
        system: Optional[list[dict]] = None,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        task_type: str = "chat",
        trace_id: Optional[str] = None,
        company_id: Optional[str] = None,
        budget_scope: Optional[str] = None,
        budget_scope_id: Optional[str] = None,
        budget_period: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        """
        Low-level messages.create wrapper with circuit breaker, retry, and cost tracking.

        Unlike ``complete()``, this accepts the full messages array, tools list,
        and returns an Anthropic-like response object — suitable for tool-calling
        loops and streaming scenarios.

        Args:
            agent_id: Calling agent ID (for cost tracking).
            model: Model name (defaults to settings.chat_model).
            max_tokens: Max output tokens.
            temperature: Sampling temperature.
            system: System prompt blocks (list of dicts).
            messages: Conversation messages.
            tools: Tool definitions for tool calling.
            task_type: Task category for logging.
            trace_id: Optional trace ID.
            company_id: Optional control-plane company for durable budget checks.
            budget_scope: Optional budget scope override (company/goal/agent/work_item).
            budget_scope_id: Optional budget scope identifier.
            budget_period: Optional budget period override (daily/monthly/quarterly/total).
            run_id: Optional control-plane agent run ID for usage linkage.

        Returns:
            Anthropic-like message response.

        Raises:
            CircuitBreakerError: When circuit breaker is open.
            Exception: On unrecoverable provider errors.
        """
        model = model or settings.chat_model
        start_time = time.time()
        run_context = get_current_run_context()
        resolved_company_id = company_id or (
            run_context.company_id if run_context is not None else None
        )
        resolved_run_id = run_id or (run_context.run_id if run_context is not None else None)

        # Budget check: downgrade model if over daily budget
        model = await self._maybe_downgrade_model(model)

        # Per-request cost cap: estimate cost and reject if too expensive
        estimated_input_tokens = self._estimate_payload_tokens(
            {
                "system": system or [],
                "messages": messages,
                "tools": tools or [],
            }
        )
        self.preflight_cost_check(
            max_tokens=max_tokens,
            model=model,
            estimated_input_tokens=estimated_input_tokens,
            cost_cap_usd=settings.llm_per_request_cost_cap_usd,
        )
        budget_reservation = await self._check_control_plane_budget(
            company_id=resolved_company_id,
            agent_id=agent_id,
            scope=budget_scope,
            scope_id=budget_scope_id,
            period=budget_period,
            model=model,
            estimated_cost_usd=self.estimate_cost(estimated_input_tokens, max_tokens, model),
            trace_id=trace_id,
        )

        # Circuit breaker check
        if not self._circuit_breaker.can_execute():
            logger.warning(
                "llm_call_rejected",
                agent_id=agent_id,
                reason="circuit_breaker_open",
            )
            raise CircuitBreakerError(
                f"LLM Gateway circuit breaker is open. "
                f"Will recover after {self._circuit_breaker.recovery_timeout}s."
            )

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            response = await self._call_messages_with_retry(kwargs, _agent_id=agent_id)
            model = kwargs["model"]

            self._circuit_breaker.record_success()

            # Cost tracking
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            latency_ms = int((time.time() - start_time) * 1000)
            cost_usd = self.estimate_cost(input_tokens, output_tokens, model)

            self._track_usage(
                agent_id=agent_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # Redis-based daily cost tracking
            await self._track_redis_cost(cost_usd)
            await self._record_control_plane_budget_usage(
                reservation=budget_reservation,
                cost_usd=cost_usd,
                model=model,
                source_agent_id=agent_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                run_id=resolved_run_id,
                trace_id=trace_id,
            )

            self._record_llm_success_metrics(
                model=model,
                agent_id=agent_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )

            logger.info(
                "llm_call_completed",
                agent_id=agent_id,
                task_type=task_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=round(cost_usd, 6),
            )

            audit_log(
                action=AuditAction.LLM_CALL,
                agent_id=agent_id,
                detail={
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": round(cost_usd, 6),
                },
                trace_id=trace_id,
            )

            return response

        except ContentSizeError:
            raise

        except Exception:
            self._circuit_breaker.record_failure()
            raise

    async def _call_messages_with_retry(self, kwargs: dict, _agent_id: str = "unknown"):
        """messages.create call with retry; delegates to _call_with_recovery."""
        return await self._call_with_recovery(kwargs, agent_id=_agent_id)

    # ------------------------------------------------------------------ #
    # Durable control-plane budget enforcement
    # ------------------------------------------------------------------ #

    def _estimate_payload_tokens(self, payload: Any) -> int:
        """Cheap, deterministic estimate for preflight budget checks."""
        import json as _json

        return max(1, len(_json.dumps(payload, ensure_ascii=False, default=str)) // 4)

    def _control_plane_llm_budget_enforced(self) -> bool:
        return getattr(settings, "control_plane_llm_budget_enforced", False) is True

    async def _check_control_plane_budget(
        self,
        *,
        company_id: str | None,
        agent_id: str,
        scope: str | None,
        scope_id: str | None,
        period: str | None,
        model: str,
        estimated_cost_usd: float,
        trace_id: str | None = None,
    ) -> ControlPlaneBudgetReservation | None:
        """Check the durable control-plane budget before spending on the provider."""
        if not self._control_plane_llm_budget_enforced():
            return None

        from shared.control_plane.budget_guard import BudgetExceededError, BudgetGuard
        from shared.control_plane.database import control_plane_db_manager
        from shared.control_plane.models import BudgetPeriod, BudgetScope
        from shared.control_plane.repository import ControlPlaneRepository

        resolved_company_id = (company_id or settings.control_plane_company_id).strip()
        if not resolved_company_id:
            raise ValueError("control_plane_company_id_required_for_llm_budget")

        scope_value = scope or settings.control_plane_llm_budget_scope
        period_value = period or settings.control_plane_llm_budget_period
        scope_member = BudgetScope(scope_value)
        period_member = BudgetPeriod(period_value)
        resolved_scope_id = scope_id
        if resolved_scope_id is None and scope_member == BudgetScope.AGENT:
            resolved_scope_id = agent_id

        async with control_plane_db_manager.session() as session:
            guard = BudgetGuard(ControlPlaneRepository(session))
            decision = await guard.check(
                company_id=resolved_company_id,
                scope=scope_member,
                period=period_member,
                scope_id=resolved_scope_id,
                model=model,
                estimated_cost_usd=estimated_cost_usd,
            )

        if not decision.allowed:
            logger.warning(
                "llm_control_plane_budget_rejected",
                agent_id=agent_id,
                company_id=resolved_company_id,
                scope=scope_member.value,
                scope_id=resolved_scope_id,
                period=period_member.value,
                model=model,
                estimated_cost_usd=round(estimated_cost_usd, 6),
                current_cost_usd=round(decision.current_cost_usd, 6),
                limit_usd=decision.limit_usd,
                reason=decision.reason,
                trace_id=trace_id,
            )
            limit_text = (
                "unlimited" if decision.limit_usd is None else f"${decision.limit_usd:.4f}"
            )
            raise BudgetExceededError(
                f"{decision.reason}: estimated_total=${decision.estimated_total_usd:.4f}, "
                f"limit={limit_text}"
            )

        if decision.budget_id is None:
            return None

        logger.info(
            "llm_control_plane_budget_allowed",
            agent_id=agent_id,
            company_id=resolved_company_id,
            budget_id=decision.budget_id,
            scope=scope_member.value,
            scope_id=resolved_scope_id,
            period=period_member.value,
            estimated_cost_usd=round(estimated_cost_usd, 6),
            trace_id=trace_id,
        )
        return ControlPlaneBudgetReservation(
            company_id=resolved_company_id,
            budget_id=decision.budget_id,
        )

    async def _record_control_plane_budget_usage(
        self,
        *,
        reservation: ControlPlaneBudgetReservation | None,
        cost_usd: float,
        model: str,
        source_agent_id: str,
        input_tokens: int,
        output_tokens: int,
        run_id: str | None,
        trace_id: str | None,
    ) -> None:
        if reservation is None and run_id is None:
            return

        try:
            from shared.control_plane.budget_guard import BudgetGuard
            from shared.control_plane.database import control_plane_db_manager
            from shared.control_plane.repository import ControlPlaneRepository

            budget_event: dict[str, Any] | None = None
            async with control_plane_db_manager.session() as session:
                repo = ControlPlaneRepository(session)
                if reservation is not None:
                    guard = BudgetGuard(repo)
                    usage = await guard.record_usage(
                        company_id=reservation.company_id,
                        budget_id=reservation.budget_id,
                        cost_usd=cost_usd,
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        run_id=run_id,
                        trace_id=trace_id,
                    )
                    budget_event = {
                        "company_id": reservation.company_id,
                        "usage_id": usage.usage_id,
                        "budget_id": reservation.budget_id,
                        "cost_usd": cost_usd,
                        "model": model,
                        "source_agent_id": source_agent_id,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "run_id": run_id,
                        "trace_id": trace_id,
                    }
                if run_id is not None:
                    run = await repo.add_agent_run_usage(
                        run_id,
                        cost_usd=cost_usd,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                    if run is None:
                        logger.warning(
                            "llm_control_plane_run_missing_for_usage",
                            run_id=run_id,
                            trace_id=trace_id,
                        )
            if budget_event is not None:
                await publish_budget_usage_recorded(**budget_event)
        except Exception as exc:
            logger.warning(
                "llm_control_plane_usage_record_failed",
                budget_id=reservation.budget_id if reservation is not None else None,
                run_id=run_id,
                cost_usd=round(cost_usd, 6),
                error=str(exc),
                error_type=type(exc).__name__,
                trace_id=trace_id,
            )

    # ------------------------------------------------------------------ #
    # Redis-based daily budget metering (COST-C02/C03)
    # ------------------------------------------------------------------ #

    async def _get_redis(self):
        """Lazy-initialize a Redis connection for cost tracking."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                )
            except Exception as exc:
                logger.warning("redis_cost_tracking_unavailable", error=str(exc))
                return None
        return self._redis

    async def _track_redis_cost(self, cost_usd: float) -> None:
        """Increment daily cost in Redis and warn if budget exceeded."""
        r = await self._get_redis()
        if r is None:
            return

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"{_REDIS_COST_KEY_PREFIX}:{today}"
        try:
            new_total = await r.incrbyfloat(key, cost_usd)
            # Set expiry to 48h if this is the first increment
            ttl = await r.ttl(key)
            if ttl == -1:
                await r.expire(key, 172_800)  # 48 hours

            # Expose daily cost to Prometheus for budget alerts
            LLM_DAILY_COST_DOLLARS.set(new_total)

            budget = settings.llm_daily_budget_usd
            if new_total > budget:
                logger.warning(
                    "llm_daily_budget_exceeded",
                    daily_total=round(new_total, 4),
                    budget=budget,
                )
        except Exception as exc:
            logger.warning("redis_cost_increment_failed", error=str(exc))

    async def get_daily_cost(self) -> float:
        """Return the accumulated LLM cost for today from Redis."""
        r = await self._get_redis()
        if r is None:
            return 0.0
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"{_REDIS_COST_KEY_PREFIX}:{today}"
        try:
            val = await r.get(key)
            return float(val) if val else 0.0
        except Exception as exc:
            logger.warning("redis_daily_cost_read_failed", error=str(exc))
            return 0.0

    async def _maybe_downgrade_model(self, requested_model: str) -> str:
        """If daily budget is exceeded, downgrade to summary_model to save costs."""
        r = await self._get_redis()
        if r is None:
            return requested_model

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"{_REDIS_COST_KEY_PREFIX}:{today}"
        try:
            val = await r.get(key)
            current_cost = float(val) if val else 0.0
        except Exception as exc:
            logger.warning("redis_budget_check_failed", error=str(exc))
            return requested_model

        if current_cost > settings.llm_daily_budget_usd:
            downgraded = settings.summary_model
            if downgraded != requested_model:
                logger.warning(
                    "llm_model_downgraded",
                    requested=requested_model,
                    downgraded_to=downgraded,
                    daily_cost=round(current_cost, 4),
                    budget=settings.llm_daily_budget_usd,
                )
            return downgraded
        return requested_model

    def _track_usage(self, agent_id: str, model: str, input_tokens: int, output_tokens: int):
        """Track usage in memory and Redis."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        # In-memory tracking (backward compat)
        if today not in self._usage_today:
            self._usage_today = {today: {}}
        if agent_id not in self._usage_today[today]:
            self._usage_today[today][agent_id] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        self._usage_today[today][agent_id]["input_tokens"] += input_tokens
        self._usage_today[today][agent_id]["output_tokens"] += output_tokens
        self._usage_today[today][agent_id]["calls"] += 1

        # Fire-and-forget Redis tracking for cross-worker accuracy
        import asyncio
        asyncio.create_task(self._track_usage_redis(today, agent_id, input_tokens, output_tokens))

    def _safe_provider_error_message(self, exc: BaseException) -> str:
        """Return operator-useful provider failure evidence without raw text."""
        category = classify_error(exc).value
        error_type = type(exc).__name__
        fingerprint = hash_identifier(str(exc), length=16)
        if fingerprint:
            return f"{category}:{error_type}:sha256:{fingerprint}"
        return f"{category}:{error_type}"

    async def _track_usage_redis(self, today: str, agent_id: str, input_tokens: int, output_tokens: int):
        """Persist usage counters in Redis HASH for cross-worker accuracy."""
        r = await self._get_redis()
        if r is None:
            return
        key = f"llm_usage:{today}:{agent_id}"
        try:
            pipe = r.pipeline()
            pipe.hincrby(key, "input_tokens", input_tokens)
            pipe.hincrby(key, "output_tokens", output_tokens)
            pipe.hincrby(key, "calls", 1)
            pipe.expire(key, 172_800)  # 48h TTL
            await pipe.execute()
        except Exception as exc:
            logger.warning("redis_usage_tracking_failed", error=str(exc))

    def get_usage_today(self, agent_id: Optional[str] = None) -> dict:
        """Return today's usage."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        if today not in self._usage_today:
            return {}

        if agent_id:
            return self._usage_today[today].get(agent_id, {})

        return self._usage_today[today]

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        """Estimate cost in USD."""
        model = model or settings.default_model
        model = self._anthropic_model_for_cost(model)

        # Claude pricing. Approximate values; check official pricing for current rates.
        pricing = {
            "claude-opus-4-6": {"input": 15.0, "output": 75.0},  # per million tokens
            "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
            "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
            "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
            "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
            "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
        }

        # Fallback: match model family prefix instead of defaulting to Opus
        rates = pricing.get(model)
        if rates is None:
            for key in pricing:
                if model.startswith(key.rsplit("-", 1)[0]):
                    rates = pricing[key]
                    break
            else:
                rates = pricing["claude-sonnet-4-20250514"]  # Safe mid-tier default

        input_cost = (input_tokens / 1_000_000) * rates["input"]
        output_cost = (output_tokens / 1_000_000) * rates["output"]

        return input_cost + output_cost

    def preflight_cost_check(
        self,
        *,
        max_tokens: int,
        model: str,
        estimated_input_tokens: int,
        cost_cap_usd: float,
    ) -> None:
        """Raise ValueError if estimated cost exceeds per-request cap."""
        estimated_cost = self.estimate_cost(estimated_input_tokens, max_tokens, model)
        if estimated_cost > cost_cap_usd:
            logger.warning(
                "llm_preflight_cost_rejected",
                estimated_cost=round(estimated_cost, 4),
                cost_cap=cost_cap_usd,
                model=model,
                input_tokens=estimated_input_tokens,
                max_output_tokens=max_tokens,
            )
            audit_log(
                action=AuditAction.COST_CAP_EXCEEDED,
                agent_id="system",
                detail={
                    "model": model,
                    "estimated_cost": round(estimated_cost, 4),
                    "cost_cap": cost_cap_usd,
                },
            )
            raise ValueError(
                f"estimated_cost_exceeds_cap: ${estimated_cost:.4f} > ${cost_cap_usd:.2f} "
                f"(model={model}, input_tokens={estimated_input_tokens}, max_output={max_tokens})"
            )

    def get_circuit_breaker_stats(self) -> dict:
        """Return circuit breaker statistics."""
        return self._circuit_breaker.get_stats()

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self._circuit_breaker.reset()


# Global LLM gateway instance
llm_gateway = LLMGateway()
