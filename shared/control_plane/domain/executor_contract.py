"""Versioned executor results; acknowledgements never mean accepted outcomes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .execution_policy import bounded_cost


class ExecutorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    status: Literal["succeeded", "failed", "accepted", "recorded"]
    summary: str = Field(max_length=20000)
    cost_usd: float = Field(ge=0)
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_references: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("cost_usd")
    @classmethod
    def _cost(cls, value: float) -> float:
        return float(bounded_cost(value))


def executor_capabilities(adapter_type: str) -> dict[str, Any]:
    local = adapter_type == "process"
    return {
        "schema_version": "1.0",
        "adapter_type": adapter_type,
        "executes_business_work": adapter_type != "builtin",
        "pause": local,
        "resume": local,
        "terminate": local,
        "automatic_crash_resume": False,
        "idempotency": "durable_dispatch_intent",
        "uncertain_effects": "operator_reconciliation",
        "output_limit_bytes": 1000000,
    }
