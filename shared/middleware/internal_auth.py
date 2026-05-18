"""Internal service authentication middleware."""

import hmac

from fastapi import Request

from shared.api import raise_internal_auth_not_configured, raise_internal_auth_unauthorized
from shared.config import settings


def _is_production() -> bool:
    return settings.app_env.lower() in {"production", "prod"}


async def verify_internal_key(request: Request):
    """Verify X-Internal-Key header for internal service calls."""
    key = request.headers.get("X-Internal-Key", "")
    expected = settings.internal_service_key.strip()
    if not expected:
        if _is_production():
            raise_internal_auth_not_configured()
        return  # Skip auth if no key configured (dev mode)
    if not hmac.compare_digest(key, expected):
        raise_internal_auth_unauthorized()
