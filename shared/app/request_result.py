"""Compatibility re-export for request result helpers."""

from shared.core.request_result import (
    UNKNOWN_ACTION_ERROR_CODE,
    request_error,
    unknown_action_error,
)

__all__ = ["UNKNOWN_ACTION_ERROR_CODE", "request_error", "unknown_action_error"]
