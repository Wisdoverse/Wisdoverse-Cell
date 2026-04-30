"""
LLM Gateway - 统一的LLM调用入口

所有Agent通过这个Gateway访问LLM，实现:
1. 统一的接口
2. 成本追踪（Redis-based daily budget metering）
3. 失败重试（指数退避）
4. 断路器（防止雪崩）
5. 持久化调用记录
6. 预算控制（超预算自动降级模型）
7. 未来可扩展支持多模型
"""
import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Optional

import anthropic
from anthropic import APIStatusError, AsyncAnthropic, RateLimitError

from ..config import settings
from ..utils.logger import get_logger
from .audit_log import AuditAction, audit_log
from .circuit_breaker import CircuitBreaker, CircuitBreakerError
from .llm_errors import (
    ContentSizeError,
    LLMErrorCategory,
    LLMRetryConfig,
    classify_error,
    default_retry_config,
)
from .metrics import (
    LLM_DAILY_COST_DOLLARS,
    LLM_ERROR_TOTAL,
    LLM_FALLBACK_TOTAL,
    LLM_REQUEST_DURATION,
)

logger = get_logger("llm_gateway")

# Redis key prefix for daily cost tracking
_REDIS_COST_KEY_PREFIX = "llm_cost"

# 可重试的 HTTP 状态码
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


@dataclass
class LLMUsageData:
    """
    LLM 调用使用数据

    用于传递给持久化回调，包含一次 LLM 调用的所有相关信息。
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


# 持久化回调类型
UsagePersistCallback = Callable[[LLMUsageData], Any]


def _is_retryable_error(exception: BaseException) -> bool:
    """
    判断是否为可重试的错误

    可重试的错误包括:
    - RateLimitError (429)
    - InternalServerError (500)
    - APIConnectionError (网络问题)
    - APIStatusError with status code in RETRYABLE_STATUS_CODES
    """
    if isinstance(exception, RateLimitError):
        return True
    if isinstance(exception, anthropic.InternalServerError):
        return True
    if isinstance(exception, anthropic.APIConnectionError):
        return True
    if isinstance(exception, APIStatusError):
        return exception.status_code in RETRYABLE_STATUS_CODES
    return False


class LLMGateway:
    """
    LLM调用网关

    特性:
    - 指数退避重试: 1s → 2s → 4s，最多重试3次
    - 断路器: 连续5次失败后打开，60秒后半开探测
    - 成本追踪: 记录每次调用的token使用量
    - 完全异步: 使用 AsyncAnthropic 客户端

    当前只支持Claude，未来可扩展支持:
    - 本地模型 (Ollama)
    - OpenAI
    - 其他模型

    使用方式:
        gateway = LLMGateway()
        response = await gateway.complete(
            prompt="提取需求...",
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
        初始化LLM网关

        Args:
            api_key: Anthropic API密钥，默认从配置读取
            base_url: Anthropic API base URL (e.g. OneAPI proxy)
            timeout: Client timeout in seconds
            failure_threshold: 断路器失败阈值
            recovery_timeout: 断路器恢复超时（秒）
        """
        self.api_key = api_key or settings.anthropic_api_key.get_secret_value()

        # Normalize base_url: strip trailing /v1 for the SDK
        resolved_base_url = base_url or settings.anthropic_base_url
        if resolved_base_url:
            resolved_base_url = resolved_base_url.rstrip("/")
            if resolved_base_url.endswith("/v1"):
                resolved_base_url = resolved_base_url[:-3]

        # Data residency check: in production, anthropic_base_url must point
        # to an approved proxy, not directly to api.anthropic.com.
        if settings.require_anthropic_proxy:
            if not resolved_base_url or "api.anthropic.com" in (resolved_base_url or ""):
                raise ValueError(
                    "ANTHROPIC_BASE_URL must be set to an approved proxy when "
                    "REQUIRE_ANTHROPIC_PROXY=true. Direct access to api.anthropic.com "
                    "is not allowed for data residency compliance."
                )

        # 使用异步客户端，避免阻塞事件循环
        self.async_client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=resolved_base_url if resolved_base_url else None,
            timeout=timeout,
        )

        # 断路器
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            name="llm_gateway"
        )

        # 成本追踪 (简化版，正式应存数据库)
        self._usage_today: dict[str, dict] = {}

        # Redis client for distributed cost tracking (lazy-initialized)
        self._redis = None

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
        persist_callback: Optional[UsagePersistCallback] = None
    ) -> str:
        """
        调用LLM完成任务

        Args:
            prompt: 用户提示词
            agent_id: 调用方Agent ID（用于成本追踪）
            task_type: 任务类型（extraction/generation/analysis/conversation）
            model: 模型名称，默认使用配置中的模型
            max_tokens: 最大输出token数
            temperature: 温度参数
            system_prompt: 系统提示词
            trace_id: 可选的追踪ID（用于关联请求）
            persist_callback: 可选的持久化回调，用于将使用记录写入数据库

        Returns:
            LLM的响应文本

        Raises:
            CircuitBreakerError: 断路器打开时
            anthropic.APIError: API调用失败且重试耗尽时
        """
        model = model or settings.default_model
        start_time = time.time()

        # 检查断路器状态
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

            # 记录成功
            self._circuit_breaker.record_success()

            # 记录使用量
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

            # Prometheus instrumentation
            LLM_REQUEST_DURATION.labels(model=model, agent_id=agent_id).observe(
                latency_ms / 1000.0
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

            # 调用持久化回调
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
                    # 持久化失败不影响主流程
                    logger.warning(
                        "llm_usage_persist_failed",
                        error=str(persist_error)
                    )

            # 提取文本响应
            return response.content[0].text

        except ContentSizeError:
            # Content-size is not a service failure — don't trip breaker
            raise

        except Exception as e:
            # All retries+fallback exhausted — record one breaker failure
            self._circuit_breaker.record_failure()
            latency_ms = int((time.time() - start_time) * 1000)
            error_message = str(e)

            logger.error(
                "llm_call_failed",
                agent_id=agent_id,
                task_type=task_type,
                model=model,
                latency_ms=latency_ms,
                error=error_message,
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
                    return await self.async_client.messages.create(**create_kwargs)
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
        """带重试的LLM调用 — delegates to _call_with_recovery."""
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
    ):
        """
        Low-level messages.create wrapper with circuit breaker, retry, and cost tracking.

        Unlike ``complete()``, this accepts the full messages array, tools list,
        and returns the raw Anthropic response object — suitable for tool-calling
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

        Returns:
            Raw Anthropic Message response.

        Raises:
            CircuitBreakerError: When circuit breaker is open.
            anthropic.APIError: On unrecoverable API errors.
        """
        model = model or settings.chat_model
        start_time = time.time()

        # Budget check: downgrade model if over daily budget
        model = await self._maybe_downgrade_model(model)

        # Per-request cost cap: estimate cost and reject if too expensive
        import json as _json
        estimated_input_tokens = len(_json.dumps(messages, ensure_ascii=False)) // 4
        self.preflight_cost_check(
            max_tokens=max_tokens,
            model=model,
            estimated_input_tokens=estimated_input_tokens,
            cost_cap_usd=settings.llm_per_request_cost_cap_usd,
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

            # Prometheus instrumentation
            LLM_REQUEST_DURATION.labels(model=model, agent_id=agent_id).observe(
                latency_ms / 1000.0
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
        """带重试的 messages.create 调用 — delegates to _call_with_recovery."""
        return await self._call_with_recovery(kwargs, agent_id=_agent_id)

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
        """追踪使用量 (内存 + Redis)"""
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
        """获取今日使用量"""
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        if today not in self._usage_today:
            return {}

        if agent_id:
            return self._usage_today[today].get(agent_id, {})

        return self._usage_today[today]

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        """估算成本（美元）"""
        model = model or settings.default_model

        # Claude定价 (大约值，实际价格请参考官方)
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
        """获取断路器统计信息"""
        return self._circuit_breaker.get_stats()

    def reset_circuit_breaker(self) -> None:
        """手动重置断路器"""
        self._circuit_breaker.reset()


# 全局LLM网关实例
llm_gateway = LLMGateway()
