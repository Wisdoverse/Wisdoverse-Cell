"""Versioned, authenticated commands crossing the evolution runtime boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillReleaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    command_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(min_length=1, max_length=64)
    company_id: str = Field(min_length=1, max_length=48)
    proposal_id: str = Field(min_length=1, max_length=48)
    evaluation_report_id: str = Field(min_length=1, max_length=48)
    evaluation_hash: str = Field(pattern="^[a-f0-9]{64}$")
    skill_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=64)
    baseline_version: int = Field(ge=1)
    candidate_version: int = Field(ge=1)
    baseline_config_hash: str = Field(pattern="^[a-f0-9]{64}$")
    candidate_config_hash: str = Field(pattern="^[a-f0-9]{64}$")
    action: Literal["shadow", "canary", "promote", "rollback"]
    traffic_pct: int = Field(default=10, ge=0, le=10)
    minimum_sample_count: int = Field(default=50, ge=50)
    approval_id: str | None = None
    expires_at: datetime


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
        ).encode()
    ).hexdigest()


def skill_config_hash(skill: Any) -> str:
    return canonical_hash(
        {
            "skill_id": skill.skill_id,
            "version": str(skill.version),
            "system_prompt": skill.system_prompt,
            "parameters": skill.parameters or {},
            "few_shot_examples": skill.few_shot_examples or [],
            "output_format": skill.output_format or "",
            "target_model": skill.target_model or "",
        }
    )


def sign_command(command: SkillReleaseCommand, secret: str) -> str:
    if len(secret) < 32:
        raise ValueError("evolution_deployment_signing_key_required")
    return hmac.new(secret.encode(), command.model_dump_json().encode(), hashlib.sha256).hexdigest()


def verify_command(command: SkillReleaseCommand, signature: str, secret: str) -> None:
    if command.expires_at.tzinfo is None or command.expires_at.astimezone(UTC) <= datetime.now(UTC):
        raise ValueError("evolution_command_expired")
    if not hmac.compare_digest(sign_command(command, secret), signature):
        raise ValueError("evolution_command_signature_invalid")
