"""Explicit capability policy for execution control and uncertain recovery."""

from .domain.execution_policy import ExecutionDenied


def validate_execution_control(adapter_type: str, action: str, state: str) -> None:
    if action not in {"pause", "resume", "terminate"}:
        raise ExecutionDenied("invalid_execution_control", 400)
    if state != "running":
        raise ExecutionDenied("execution_not_running")
    if adapter_type != "process":
        raise ExecutionDenied("executor_control_not_supported", 409)
