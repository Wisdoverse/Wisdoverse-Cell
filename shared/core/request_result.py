"""Shared request result helpers for application use cases."""

from typing import Any

UNKNOWN_ACTION_ERROR_CODE = "unknown_action"


def request_error(message: str, error_code: str, **extra: Any) -> dict[str, Any]:
    """Return a stable application-level error payload."""
    result: dict[str, Any] = {"error": message, "error_code": error_code}
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def unknown_action_error(**extra: Any) -> dict[str, Any]:
    """Return the standard error payload for unsupported agent request actions."""
    return request_error("unknown action", UNKNOWN_ACTION_ERROR_CODE, **extra)
