"""Versioned executor results; acknowledgements never mean accepted outcomes."""

from __future__ import annotations

from typing import Any

from shared.protocols.executor import ExecutorResponse as ExecutorResponse


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
