"""Provider-style exceptions for LLM retry tests without SDK dependencies."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock


class ProviderAPIError(Exception):
    def __init__(
        self,
        message: str = "",
        *,
        response: Any = None,
        body: Any = None,
        request: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.response = response or Mock(status_code=None)
        self.status_code = getattr(self.response, "status_code", None)
        self.body = body
        self.request = request


class APIError(ProviderAPIError):
    pass


class APIStatusError(ProviderAPIError):
    pass


class RateLimitError(APIStatusError):
    pass


class InternalServerError(APIStatusError):
    pass


class BadRequestError(APIStatusError):
    pass


class AuthenticationError(APIStatusError):
    pass


class PermissionDeniedError(APIStatusError):
    pass


class APIConnectionError(ProviderAPIError):
    pass


anthropic_like = SimpleNamespace(
    APIError=APIError,
    APIStatusError=APIStatusError,
    RateLimitError=RateLimitError,
    InternalServerError=InternalServerError,
    BadRequestError=BadRequestError,
    AuthenticationError=AuthenticationError,
    PermissionDeniedError=PermissionDeniedError,
    APIConnectionError=APIConnectionError,
)
