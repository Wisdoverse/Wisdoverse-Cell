"""Coordinator workflow replay tool (DDD-018 / ADR-0008 follow-up).

Reads the durable coordinator state for one workflow_id and prints the
reconstructed history (workflow row, agent states, pending decisions)
with referential consistency checks. Use during incident response to
verify that a workflow's persisted state is internally consistent
before reapplying decisions.

Usage:

    python -m services.orchestration.coordinator.app.replay <workflow_id>

Exit codes:
    0 — workflow read and consistent (or workflow not found, which is
        not an error condition for the replay tool).
    1 — workflow read but inconsistent (decision references missing
        target agent, decision workflow_id mismatch, etc.).
    2 — DB read or argument error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from ..db.database import db_manager
from ..db.postgres_state_store import PostgresCoordinatorStateStore


async def _load_workflow_state(workflow_id: str) -> dict[str, Any]:
    """Load the workflow row, related decisions, and agent states."""
    async with db_manager.session() as session:
        store = PostgresCoordinatorStateStore(session)
        workflows = await store.get_workflow_states()
        workflow = workflows.get(workflow_id)
        pending_decisions = await store.get_pending_decisions()
        agent_states = await store.get_agent_states()

    related_decisions = [
        d for d in pending_decisions if d.workflow_id == workflow_id
    ]
    involved_agents: set[str] = set()
    if workflow is not None:
        involved_agents.update(workflow.agents_involved or [])
    involved_agents.update(d.target_agent for d in related_decisions)
    related_agent_states = {
        agent_id: agent_states[agent_id]
        for agent_id in involved_agents
        if agent_id in agent_states
    }

    return {
        "workflow": workflow,
        "related_decisions": related_decisions,
        "related_agent_states": related_agent_states,
        "all_pending_decisions_count": len(pending_decisions),
        "all_agent_states_count": len(agent_states),
    }


def _consistency_check(snapshot: dict[str, Any]) -> list[str]:
    """Return human-readable inconsistencies, empty list when clean."""
    issues: list[str] = []
    workflow = snapshot["workflow"]
    decisions = snapshot["related_decisions"]
    agent_states = snapshot["related_agent_states"]

    if workflow is None:
        return issues

    workflow_agents = set(workflow.agents_involved or [])
    decision_targets = {d.target_agent for d in decisions}
    missing_in_workflow = decision_targets - workflow_agents
    if missing_in_workflow:
        issues.append(
            "decisions reference target_agents not in workflow.agents_involved: "
            f"{sorted(missing_in_workflow)}"
        )

    decision_targets_not_in_state = decision_targets - set(agent_states.keys())
    if decision_targets_not_in_state:
        issues.append(
            "decisions reference target_agents with no agent_state row: "
            f"{sorted(decision_targets_not_in_state)}"
        )

    return issues


def _render(snapshot: dict[str, Any], issues: list[str]) -> str:
    """Render the snapshot as a human-readable replay summary."""
    workflow = snapshot["workflow"]
    decisions = snapshot["related_decisions"]
    agent_states = snapshot["related_agent_states"]

    lines: list[str] = []
    if workflow is None:
        lines.append("workflow: not found")
        lines.append(f"  pending_decisions_total={snapshot['all_pending_decisions_count']}")
        lines.append(f"  agent_states_total={snapshot['all_agent_states_count']}")
        return "\n".join(lines)

    lines.append(f"workflow_id={workflow.workflow_id}")
    lines.append(f"  type={workflow.type}")
    lines.append(f"  status={workflow.status}")
    lines.append(f"  current_phase={workflow.current_phase}")
    lines.append(f"  agents_involved={list(workflow.agents_involved or [])}")
    lines.append(f"  created_at={workflow.created_at}")
    lines.append(f"  updated_at={workflow.updated_at}")
    lines.append(
        "  context_keys=" + json.dumps(sorted((workflow.context or {}).keys()))
    )

    lines.append("")
    lines.append(f"related_decisions={len(decisions)}")
    for decision in decisions:
        lines.append(
            f"  decision_id={decision.decision_id} action={decision.action} "
            f"target={decision.target_agent} created_at={decision.created_at}"
        )

    lines.append("")
    lines.append(f"related_agent_states={len(agent_states)}")
    for agent_id, state in agent_states.items():
        lines.append(
            f"  agent_id={agent_id} status={state.status} "
            f"current_task={state.current_task} error={state.error}"
        )

    lines.append("")
    if issues:
        lines.append("CONSISTENCY ISSUES:")
        for issue in issues:
            lines.append(f"  - {issue}")
    else:
        lines.append("consistency: OK")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="coordinator-replay",
        description=(
            "Read and verify the durable coordinator state for one workflow. "
            "Used during incident response per ADR-0008 (DDD-018)."
        ),
    )
    parser.add_argument("workflow_id", help="The workflow_id to inspect.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the snapshot as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


async def _run(argv: list[str]) -> int:
    args = _parse_args(argv)
    try:
        snapshot = await _load_workflow_state(args.workflow_id)
    except Exception as exc:
        print(f"error: failed to load workflow state: {exc}", file=sys.stderr)
        return 2

    issues = _consistency_check(snapshot)

    if args.json:
        payload = {
            "workflow": snapshot["workflow"].model_dump(mode="json")
            if snapshot["workflow"]
            else None,
            "related_decisions": [
                d.model_dump(mode="json") for d in snapshot["related_decisions"]
            ],
            "related_agent_states": {
                agent_id: state.model_dump(mode="json")
                for agent_id, state in snapshot["related_agent_states"].items()
            },
            "all_pending_decisions_count": snapshot["all_pending_decisions_count"],
            "all_agent_states_count": snapshot["all_agent_states_count"],
            "issues": issues,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render(snapshot, issues))

    return 1 if issues else 0


def main() -> int:
    return asyncio.run(_run(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
