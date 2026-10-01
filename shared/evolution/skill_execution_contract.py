"""Frozen skill selection and task-local evidence for actual LLM execution."""

from __future__ import annotations

import hashlib
import hmac
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .release_contract import canonical_hash

if TYPE_CHECKING:
    from .trace_collector import TraceHandle


class SkillSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    company_id: str = Field(min_length=1, max_length=48)
    agent_id: str = Field(min_length=1, max_length=64)
    skill_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=64)


class SkillSelection(SkillSelectionRequest):
    schema_version: Literal["1.0"] = "1.0"
    deployment_id: str
    experiment_id: str | None
    version: int = Field(ge=1)
    configuration_hash: str = Field(pattern="^[a-f0-9]{64}$")
    configuration: dict[str, Any]
    expires_at: datetime
    signature: str = Field(pattern="^[a-f0-9]{64}$")


class SkillExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    selection: SkillSelection
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    success: bool


def selection_signature(selection: dict[str, Any], secret: str) -> str:
    if len(secret) < 32:
        raise ValueError("evolution_deployment_signing_key_required")
    digest = canonical_hash({key: value for key, value in selection.items() if key != "signature"})
    return hmac.new(secret.encode(), digest.encode(), hashlib.sha256).hexdigest()


def verify_selection(selection: SkillSelection, secret: str) -> None:
    if selection.expires_at.tzinfo is None or selection.expires_at.astimezone(UTC) <= datetime.now(
        UTC
    ):
        raise ValueError("evolution_skill_selection_expired")
    if not hmac.compare_digest(
        selection.signature, selection_signature(selection.model_dump(mode="json"), secret)
    ):
        raise ValueError("evolution_skill_selection_signature_invalid")
    if canonical_hash(selection.configuration) != selection.configuration_hash:
        raise ValueError("evolution_skill_configuration_hash_mismatch")


current_evolution_trace: ContextVar[TraceHandle | None] = ContextVar(
    "evolution_execution_trace", default=None
)
