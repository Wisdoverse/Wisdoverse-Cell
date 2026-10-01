"""Server-owned operator identities and least-privilege company scopes."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from shared.api import raise_control_plane_api_error
from shared.config import settings


class OperatorGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    actor_id: str = Field(min_length=1, max_length=128)
    token_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    companies: list[str] = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1, max_length=100)
    role_ids: list[str] = Field(default_factory=list, max_length=200)


@dataclass(frozen=True, slots=True)
class OperatorPrincipal:
    actor_id: str
    company_scopes: frozenset[str]
    scopes: frozenset[str]
    role_ids: frozenset[str] = frozenset()

    def require(self, action: str, company_id: str) -> None:
        if (
            "*" not in self.company_scopes
            and company_id not in self.company_scopes
            or "*" not in self.scopes
            and action not in self.scopes
        ):
            raise_control_plane_api_error(status_code=403, detail="operator_scope_denied")


_current_operator: ContextVar[OperatorPrincipal | None] = ContextVar(
    "control_plane_operator", default=None
)


def current_operator() -> OperatorPrincipal | None:
    return _current_operator.get()


async def require_operator(request: Request) -> OperatorPrincipal:
    cached = getattr(request.state, "control_plane_operator", None)
    if isinstance(cached, OperatorPrincipal):
        return cached
    configured = settings.control_plane_operators_json.strip()
    if not configured:
        if settings.app_env.lower() not in {"development", "dev", "test", "testing"}:
            raise_control_plane_api_error(status_code=503, detail="operator_auth_not_configured")
        principal = OperatorPrincipal("development:board", frozenset({"*"}), frozenset({"*"}))
    else:
        token = request.headers.get("X-Control-Plane-Operator-Token", "")
        if not token:
            raise_control_plane_api_error(status_code=401, detail="operator_token_required")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        try:
            entries = json.loads(configured)
            if not isinstance(entries, list) or not entries:
                raise ValueError("invalid operator configuration")
            grants = [OperatorGrant.model_validate(entry) for entry in entries]
            matches = [
                entry for entry in grants if hmac.compare_digest(entry.token_sha256, token_hash)
            ]
            if len(matches) != 1:
                raise_control_plane_api_error(status_code=401, detail="operator_token_invalid")
            entry = matches[0]
            principal = OperatorPrincipal(
                entry.actor_id,
                frozenset(entry.companies),
                frozenset(entry.scopes),
                frozenset(entry.role_ids),
            )
        except (KeyError, ValueError, TypeError):
            raise_control_plane_api_error(
                status_code=503, detail="operator_auth_configuration_invalid"
            )
    request.state.control_plane_operator = principal
    return principal


def _action(method: str, path: str) -> str:
    if method in {"GET", "HEAD"}:
        if path.endswith("/audit-export"):
            return "audit:export"
        return "knowledge:read" if "/knowledge" in path else "control-plane:read"
    if "/knowledge" in path:
        return "knowledge:delete" if method == "DELETE" else "knowledge:write"
    if path.endswith(("/run", "/retry", "/wake", "/run-once")):
        return "work:execute"
    if "/approvals/" in path:
        return "approval:resolve"
    if "/company-templates/import" in path:
        return "template:import"
    if "/evolution-proposals" in path:
        return "evolution:write"
    if "/agents" in path:
        return "agent:write"
    if "/budgets" in path or "/budget-usage" in path:
        return "budget:write"
    if "/executions" in path:
        return "execution:control" if path.endswith("/control") else "execution:recover"
    return "work:write"


async def authorize_control_plane_request(request: Request) -> AsyncGenerator[None, None]:
    principal = await require_operator(request)
    body: dict[str, Any] = {}
    if request.method not in {"GET", "HEAD", "DELETE"}:
        try:
            value = await request.json()
            body = value if isinstance(value, dict) else {}
        except (ValueError, UnicodeDecodeError):
            pass  # Route schema owns malformed request validation.
    company_id = (
        request.path_params.get("company_id")
        or request.query_params.get("company_id")
        or body.get("company_id")
        or settings.control_plane_company_id
    )
    principal.require(_action(request.method, request.url.path), str(company_id))
    # Cross-company directory and new-company creation are board capabilities.
    if request.url.path.endswith("/companies") or "/company-templates/import" in request.url.path:
        principal.require("company:directory", "*")
    token = _current_operator.set(principal)
    try:
        yield
    finally:
        _current_operator.reset(token)
