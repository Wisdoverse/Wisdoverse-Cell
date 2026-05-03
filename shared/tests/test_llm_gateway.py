"""
LLM Gateway 单元测试

测试覆盖:
1. 重试机制 - 指数退避
2. 断路器集成
3. 可重试/不可重试错误
4. 成本追踪
"""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from shared.infra.circuit_breaker import CircuitBreakerError, CircuitState
from shared.infra.llm_gateway import RETRYABLE_STATUS_CODES, LLMGateway
from tests.helpers.provider_errors import anthropic_like as anthropic

APIStatusError = anthropic.APIStatusError
RateLimitError = anthropic.RateLimitError


class MockResponse:
    """模拟 Anthropic API 响应"""

    def __init__(self, text: str = "Test response", input_tokens: int = 10, output_tokens: int = 20):
        self.content = [Mock(text=text)]
        self.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)


class TestLLMGatewayBasic:
    """基础功能测试"""

    @pytest.fixture
    def gateway(self):
        """创建测试用 gateway"""
        with patch('shared.infra.llm_gateway.settings') as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.default_model = "claude-sonnet-4-20250514"
            mock_settings.anthropic_base_url = ""
            mock_settings.require_anthropic_proxy = False
            gateway = LLMGateway(api_key="test-key")
            yield gateway

    @pytest.mark.asyncio
    async def test_successful_call(self, gateway):
        """成功调用应返回响应"""
        gateway.async_client.messages.create = AsyncMock(return_value=MockResponse("Hello"))

        result = await gateway.complete(
            prompt="Test prompt",
            agent_id="test-agent"
        )

        assert result == "Hello"
        gateway.async_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_tracks_usage(self, gateway):
        """应追踪使用量"""
        gateway.async_client.messages.create = AsyncMock(
            return_value=MockResponse(input_tokens=100, output_tokens=50)
        )

        await gateway.complete(prompt="Test", agent_id="test-agent")

        usage = gateway.get_usage_today("test-agent")
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["calls"] == 1

    def test_estimate_cost(self, gateway):
        """应正确估算成本"""
        # claude-sonnet-4: $3/M input, $15/M output
        cost = gateway.estimate_cost(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="claude-sonnet-4-20250514"
        )

        assert cost == 18.0  # $3 + $15


class TestLLMGatewayRetry:
    """重试机制测试"""

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
        """429 错误应重试"""
        # 前两次失败，第三次成功
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
        """500 错误应重试"""
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
        """400 错误不应重试"""
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

        # 只调用一次，没有重试
        assert gateway.async_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, gateway):
        """超过最大重试次数应抛出异常"""
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

        # rate_limit 分类默认总共尝试 6 次
        assert gateway.async_client.messages.create.call_count == 6


class TestLLMGatewayCircuitBreaker:
    """断路器集成测试"""

    @pytest.fixture
    def gateway(self):
        mock_logger = MagicMock()
        with patch('shared.infra.llm_gateway.settings') as mock_settings, \
             patch('shared.infra.llm_gateway.logger', mock_logger):
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.default_model = "claude-sonnet-4-20250514"
            mock_settings.anthropic_base_url = ""
            mock_settings.require_anthropic_proxy = False
            # 低阈值便于测试
            gateway = LLMGateway(
                api_key="test-key",
                failure_threshold=2,
                recovery_timeout=60
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, gateway):
        """连续失败后断路器应打开"""
        # 使用 InternalServerError 代替 APIConnectionError，因为后者构造函数签名变化
        error_response = Mock(status_code=500)
        gateway.async_client.messages.create = AsyncMock(
            side_effect=anthropic.InternalServerError("Server error", response=error_response, body={})
        )

        # 触发失败（需要多次因为有重试机制，每次调用会重试4次）
        for _ in range(2):
            try:
                await gateway.complete(prompt="Test", agent_id="test-agent")
            except Exception:
                pass

        # 断路器应该打开
        stats = gateway.get_circuit_breaker_stats()
        assert stats["state"] == "open"

    @pytest.mark.asyncio
    async def test_rejects_when_circuit_open(self, gateway):
        """断路器打开时应拒绝请求"""
        error_response = Mock(status_code=500)
        gateway.async_client.messages.create = AsyncMock(
            side_effect=anthropic.InternalServerError("Server error", response=error_response, body={})
        )

        # 触发断路器打开
        for _ in range(2):
            try:
                await gateway.complete(prompt="Test", agent_id="test-agent")
            except Exception:
                pass

        # 后续请求应被拒绝
        with pytest.raises(CircuitBreakerError):
            await gateway.complete(prompt="Test", agent_id="test-agent")

    @pytest.mark.asyncio
    async def test_circuit_closes_on_success(self, gateway):
        """成功后断路器应关闭"""
        gateway.async_client.messages.create = AsyncMock(return_value=MockResponse("Success"))

        await gateway.complete(prompt="Test", agent_id="test-agent")

        stats = gateway.get_circuit_breaker_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0

    def test_reset_circuit_breaker(self, gateway):
        """应能手动重置断路器"""
        # 模拟断路器打开
        gateway._circuit_breaker._state = CircuitState.OPEN
        gateway._circuit_breaker._failure_count = 5

        gateway.reset_circuit_breaker()

        stats = gateway.get_circuit_breaker_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0


class TestRetryableStatusCodes:
    """可重试状态码测试"""

    def test_retryable_codes(self):
        """验证可重试状态码列表"""
        assert 429 in RETRYABLE_STATUS_CODES  # Rate limit
        assert 500 in RETRYABLE_STATUS_CODES  # Internal server error
        assert 502 in RETRYABLE_STATUS_CODES  # Bad gateway
        assert 503 in RETRYABLE_STATUS_CODES  # Service unavailable
        assert 529 in RETRYABLE_STATUS_CODES  # Overloaded

    def test_non_retryable_codes(self):
        """验证不可重试状态码"""
        assert 400 not in RETRYABLE_STATUS_CODES  # Bad request
        assert 401 not in RETRYABLE_STATUS_CODES  # Unauthorized
        assert 403 not in RETRYABLE_STATUS_CODES  # Forbidden
        assert 404 not in RETRYABLE_STATUS_CODES  # Not found
