"""Deprecated location for control-plane agent-run lifecycle.

The lifecycle helpers moved to
``shared.control_plane.domain.lifecycle.agent_run_lifecycle`` as part of
Migration Plan §Stage 1 item 2. New imports should use the new path.
This shim preserves backward compatibility until callers migrate.
"""

from shared.control_plane.domain.lifecycle.agent_run_lifecycle import (
    AgentWakeupRunRecord,
    append_agent_run_audit,
    build_agent_wakeup_completion_event,
    complete_agent_wakeup_run,
    fail_agent_wakeup_run,
    start_agent_wakeup_run,
)

__all__ = [
    "AgentWakeupRunRecord",
    "append_agent_run_audit",
    "build_agent_wakeup_completion_event",
    "complete_agent_wakeup_run",
    "fail_agent_wakeup_run",
    "start_agent_wakeup_run",
]
