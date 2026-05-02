"""Async-local control-plane execution context."""

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPlaneRunContext:
    company_id: str
    run_id: str
    agent_id: str
    trace_id: str | None = None
    goal_id: str | None = None
    work_item_id: str | None = None


_current_run_context: ContextVar[ControlPlaneRunContext | None] = ContextVar(
    "control_plane_run_context",
    default=None,
)


def get_current_run_context() -> ControlPlaneRunContext | None:
    return _current_run_context.get()


def set_current_run_context(
    context: ControlPlaneRunContext,
) -> Token[ControlPlaneRunContext | None]:
    return _current_run_context.set(context)


def reset_current_run_context(token: Token[ControlPlaneRunContext | None]) -> None:
    _current_run_context.reset(token)
