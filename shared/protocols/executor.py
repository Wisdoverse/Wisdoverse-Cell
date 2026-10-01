"""Portable versioned executor wire contracts; receipts are not outcome acceptance."""

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    company_id: str = Field(min_length=1, max_length=48)
    action: str = Field(min_length=1, max_length=64)
    agent_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=48)
    trace_id: str | None = Field(default=None, min_length=1, max_length=96)
    goal_id: str | None = Field(default=None, min_length=1, max_length=48)
    work_item_id: str | None = Field(default=None, min_length=1, max_length=48)
    input: dict[str, Any]
    max_cost_usd: float = Field(ge=0, le=1000000)

    @field_validator("max_cost_usd")
    @classmethod
    def _finite_cost(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("executor_cost_must_be_finite")
        return value

    @field_validator("input")
    @classmethod
    def _json_input(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        json.dumps(value, allow_nan=False)
        return value


class ExecutorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    status: Literal["succeeded", "failed", "accepted", "recorded"]
    summary: str = Field(max_length=20000)
    cost_usd: float = Field(ge=0)
    cost_is_estimate: bool = False
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_references: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("cost_usd")
    @classmethod
    def _cost(cls, value: float) -> float:
        if not math.isfinite(value) or value > 1000000:
            raise ValueError("executor_cost_out_of_bounds")
        return value


class ExecutorCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    runtime_id: str
    company_id: str
    enabled: bool
    actions: list[str]
    idempotency: Literal["owner_local_durable_request_and_receipt"] = (
        "owner_local_durable_request_and_receipt"
    )
    automatic_crash_resume: Literal[False] = False
    business_outcome_acceptance: Literal["separate_control_plane_review"] = (
        "separate_control_plane_review"
    )
    cost_metering: Literal["reserved_ceiling_estimate"] = "reserved_ceiling_estimate"
    timeout_seconds: int
    input_limit_bytes: Literal[1000000] = 1000000
    output_limit_bytes: Literal[1000000] = 1000000


class ExecutorReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    runtime_id: str
    company_id: str
    run_id: str
    state: str
    response: ExecutorResponse | None
