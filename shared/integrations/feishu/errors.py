"""
Feishu Error Handling - 统一错误处理模块

包含：
- FeishuAPIError: 飞书 API 错误异常
- retryable_request: 带重试的 HTTP 请求（已废弃，SDK 内置重试）
- handle_feishu_response: 响应处理工具
- feishu_error_handler: 错误处理装饰器
"""
import asyncio
import functools
import warnings
from typing import Any, Callable, Optional

from shared.utils.logger import get_logger

logger = get_logger("feishu.errors")


# 可重试的 HTTP 状态码
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# 可重试的飞书错误码
RETRYABLE_FEISHU_CODES = {
    99991663,  # Token expired, need refresh
    99991664,  # Token invalid
    99991668,  # Rate limited
}


class FeishuAPIError(Exception):
    """
    飞书 API 错误异常

    Attributes:
        code: 飞书错误码
        message: 错误消息
        details: 额外详情
    """

    def __init__(
        self,
        code: int = 0,
        message: str = "",
        details: Optional[dict] = None
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return f"FeishuAPIError [{self.code}]: {self.message}"

    @classmethod
    def from_response(cls, response_data: dict) -> "FeishuAPIError":
        """从 API 响应创建异常"""
        code = response_data.get("code", 0)
        message = response_data.get("msg", response_data.get("message", "Unknown error"))
        return cls(code=code, message=message, details=response_data)

    @property
    def is_retryable(self) -> bool:
        """是否可重试"""
        return self.code in RETRYABLE_FEISHU_CODES


async def retryable_request(
    method: str,
    url: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs,
):
    """
    带重试机制的 HTTP 请求

    .. deprecated::
        SDK (lark-oapi) 内置重试机制，不再需要手动重试。
        此函数保留仅为向后兼容。

    Args:
        method: HTTP 方法 (get, post, patch, etc.)
        url: 请求 URL
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
        **kwargs: 传递给 httpx 的其他参数

    Returns:
        httpx.Response

    Raises:
        FeishuAPIError: 重试耗尽后抛出
    """
    warnings.warn(
        "retryable_request is deprecated. Use lark-oapi SDK which has built-in retry.",
        DeprecationWarning,
        stacklevel=2,
    )
    import httpx

    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                request_method = getattr(client, method.lower())
                response = await request_method(url, **kwargs)

                # Check if status code is retryable
                if response.status_code in RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "retryable_status_code",
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        url=url
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue

                # Check for retryable Feishu error codes in response body
                try:
                    data = response.json()
                    feishu_code = data.get("code", 0)
                    if feishu_code in RETRYABLE_FEISHU_CODES:
                        logger.warning(
                            "retryable_feishu_code",
                            feishu_code=feishu_code,
                            attempt=attempt + 1,
                            url=url
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                            continue
                except Exception:
                    pass  # JSON parsing failed, rely on status code check

                return response

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_error = e
            logger.warning(
                "request_connection_error",
                error=str(e),
                attempt=attempt + 1,
                url=url
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue

    # All retries exhausted
    error_msg = str(last_error) if last_error else "Max retries exceeded"
    logger.error(
        "request_retries_exhausted",
        url=url,
        max_retries=max_retries,
        error=error_msg
    )
    raise FeishuAPIError(
        code=-1,
        message=f"Request failed after {max_retries} retries: {error_msg}"
    )


def handle_feishu_response(response_data: dict) -> Any:
    """
    处理飞书 API 响应

    Args:
        response_data: API 响应数据

    Returns:
        data 字段的内容

    Raises:
        FeishuAPIError: 如果响应表示错误
    """
    code = response_data.get("code", 0)

    if code != 0:
        error = FeishuAPIError.from_response(response_data)
        logger.error(
            "feishu_api_error",
            code=code,
            message=response_data.get("msg", ""),
        )
        raise error

    return response_data.get("data")


def feishu_error_handler(operation_name: str):
    """
    飞书操作错误处理装饰器

    自动捕获异常并转换为 FeishuAPIError。

    Args:
        operation_name: 操作名称（用于日志）

    Usage:
        @feishu_error_handler("send_card")
        async def send_card(...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except FeishuAPIError:
                # Re-raise FeishuAPIError as is
                raise
            except Exception as e:
                logger.error(
                    "feishu_operation_error",
                    operation=operation_name,
                    error_type=type(e).__name__,
                    error=str(e)
                )
                raise FeishuAPIError(
                    code=-1,
                    message=f"{operation_name} failed: {str(e)}"
                ) from e
        return wrapper
    return decorator
