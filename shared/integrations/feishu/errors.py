"""
Feishu error handling utilities.

Includes:
- FeishuAPIError: Feishu API exception.
- retryable_request: deprecated HTTP retry helper; the SDK has built-in retry.
- handle_feishu_response: response handling helper.
- feishu_error_handler: error handling decorator.
"""
import asyncio
import functools
import warnings
from typing import Any, Callable, Optional

from shared.utils.logger import get_logger

logger = get_logger("feishu.errors")


# Retryable HTTP status codes.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Retryable Feishu error codes.
RETRYABLE_FEISHU_CODES = {
    99991663,  # Token expired, need refresh
    99991664,  # Token invalid
    99991668,  # Rate limited
}


class FeishuAPIError(Exception):
    """
    Feishu API error.

    Attributes:
        code: Feishu error code.
        message: Error message.
        details: Additional details.
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
        """Create an exception from an API response."""
        code = response_data.get("code", 0)
        message = response_data.get("msg", response_data.get("message", "Unknown error"))
        return cls(code=code, message=message, details=response_data)

    @property
    def is_retryable(self) -> bool:
        """Return whether the error is retryable."""
        return self.code in RETRYABLE_FEISHU_CODES


async def retryable_request(
    method: str,
    url: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs,
):
    """
    HTTP request helper with retries.

    .. deprecated::
        The lark-oapi SDK has built-in retry support. This function remains only
        for backward compatibility.

    Args:
        method: HTTP method such as get, post, or patch.
        url: Request URL.
        max_retries: Maximum retry attempts.
        retry_delay: Retry delay in seconds.
        **kwargs: Additional parameters passed to httpx.

    Returns:
        httpx.Response

    Raises:
        FeishuAPIError: Raised after retry exhaustion.
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
    Handle a Feishu API response.

    Args:
        response_data: API response data.

    Returns:
        The content of the data field.

    Raises:
        FeishuAPIError: Raised when the response represents an error.
    """
    code = response_data.get("code", 0)

    if code != 0:
        error = FeishuAPIError.from_response(response_data)
        logger.error(
            "feishu_api_error",
            code=code,
            platform_message_length=len(str(response_data.get("msg", ""))),
        )
        raise error

    return response_data.get("data")


def feishu_error_handler(operation_name: str):
    """
    Error handling decorator for Feishu operations.

    Captures exceptions and converts them to FeishuAPIError.

    Args:
        operation_name: Operation name used for logs.

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
