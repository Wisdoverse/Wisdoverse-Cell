# Coordinator

Cross-boundary orchestration worker. Classifies inbound events and
dispatches typed decisions to the right runtime agent. Maintains a
scratchpad and short-term state for coordination across runs.

Canonical runtime ID: `coordinator`.
See [`docs/architecture/module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.8.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `services/orchestration/coordinator/` |
| Owned tables | `coordinator_event_outbox` (durable); `coordinator_agent_state` / `coordinator_workflow_state` / `coordinator_pending_decision` (durable when `COORDINATOR_DURABLE_STATE=true`). |
| Aggregate root / policies | `core/domain/workflow_state.py` `CoordinatorWorkflowState` owns workflow lifecycle rules; `core/domain/dispatch.py` `CoordinatorDispatchPolicy` owns dispatch-target contracts; `core/domain/scratchpad.py` `CoordinatorScratchpadConsistencyPolicy` owns the decision-store-before-scratchpad projection rule. |
| ACL ports | `core/event_use_cases.py` `CoordinatorThinkerPort` (LLM thinker — DDD-019 landed) |
| State store | `core/state_ports.py` `CoordinatorStateStorePort` Protocol; in-memory adapter (`db/state_store.py`) for tests + dev; production uses `db/postgres_state_store.py` `PostgresCoordinatorStateStore` when `COORDINATOR_DURABLE_STATE=true` (ADR-0008). Workflow-state writes are validated through `CoordinatorWorkflowState`; agent-state and decision rows are normalized through `CoordinatorAgentStateRecord` and `CoordinatorDecisionRecord` before leaving adapters. |
| Scratchpad | `core/event_use_cases.py` `CoordinatorScratchpadPort` Protocol. The scratchpad is a derived reasoning projection: decisions persist through the state-store/UoW boundary first, then `CoordinatorScratchpadProjectionPlan` is applied and compaction is scheduled only after the projection is safe. |
| Domain events | Inbound classified via `core/classifier.py`; outbound decisions are converted to `CoordinatorDispatchEnvelope` by `core/domain/dispatch.py` and then to EventBus events by `core/dispatcher.py`. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Classified event** | An inbound EventBus event tagged with a `kind` (e.g. `progress`, `chat`, `coordinator-dispatch`) by `classifier.py`. |
| **Decision** | A typed instruction the coordinator emits for downstream agents (e.g. "Dev should start task X"). Drained from the LLM thinker. |
| **Decision record** | The persisted pending-decision snapshot. `CoordinatorDecisionRecord` owns typed decision, workflow, target-agent, and task identifiers before replay or thinker context consumes it. |
| **Workflow state** | The aggregate for one orchestration workflow, including status, current phase, involved agents, context, and status-change events. |
| **Dispatch route** | The target-agent relationship and event contract selected for a decision. Owned by `CoordinatorDispatchPolicy`. |
| **Scratchpad** | The short-term reasoning context the coordinator presents to the thinker. It is a derived projection of persisted decisions and workflow/agent state, not the consistency source. |
| **Agent state** | Per-agent runtime status (working / idle / current-task) cached by the coordinator for use in the next thinker context. `CoordinatorAgentStateRecord` owns the typed agent id and status vocabulary. |
| **Thinker** | The LLM-backed planner. Behind `CoordinatorThinkerPort` (DDD-019). |
| **Dispatch envelope** | The primitive event contract selected by the dispatch policy before EventBus publication. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.8:

- **Upstream**: Open-Host Service to all runtime agents (consumes their events).
- **Downstream**: Customer/Supplier to all runtime agents (emits dispatch decisions).
- **ACL** to LLM via `CoordinatorThinkerPort` (DDD-019 landed) + `shared.infra.llm_gateway`.
- **Conformist** to Control Plane.

## Architecture

```
core/
  application_facade.py     composes use cases for the service shell
  event_use_cases.py        CoordinatorEventUseCase + ThinkerPort + ScratchpadPort
  domain/dispatch.py        dispatch target value objects + dispatch policy
  domain/scratchpad.py      scratchpad projection consistency policy
  domain/state_records.py   typed agent-state + pending-decision records
  domain/workflow_state.py  workflow lifecycle aggregate + status events
  classifier.py             inbound event → ClassifiedEvent
  dispatcher.py             DispatchEnvelope → EventBus event
  state_ports.py            CoordinatorStateStorePort Protocol
  outbox_ports.py
  outbox_delivery_use_cases.py
  health_ports.py / health_use_cases.py
  think.py                  thinker implementation (LLM-backed)
  models.py                 Decision + state record DTOs
db/
  state_store.py            in-memory adapter (DDD-018 introduces durable adapter)
  outbox_store.py
  repository.py
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.10.

## Runbook: Replay Tool

`services/orchestration/coordinator/app/replay.py` is an incident-
response command that reads the durable Postgres state for one
workflow and prints the reconstructed history with referential
consistency checks. Use it whenever the coordinator's behaviour
for a specific workflow looks wrong: the workflow appears stuck,
a decision targets the wrong agent, or an agent's state and the
workflow's `agents_involved` list disagree.

```bash
# Human-readable summary (default).
python -m services.orchestration.coordinator.app.replay <workflow_id>

# Machine-readable JSON (pipe to jq / log shipping).
python -m services.orchestration.coordinator.app.replay <workflow_id> --json
```

What the tool reports:

- The `coordinator_workflow_state` row for the workflow (type,
  status, current phase, agents involved, context keys, timestamps).
- All pending decisions referencing this workflow (`coordinator_pending_decision`).
- Agent-state rows for every agent referenced either by the
  workflow row or by any of its decisions
  (`coordinator_agent_state`).
- Two consistency checks:
  1. **Stray decision targets**: any decision whose `target_agent`
     is not listed in `workflow.agents_involved`. Usually means a
     missed `update_workflow_state` write.
  2. **Missing agent_state**: any decision target with no row in
     `coordinator_agent_state`. Usually means an agent crashed
     before its first state write.

Exit codes:

- `0` — workflow read successfully and consistent (or the
  workflow was not found, which is a valid "nothing to do" outcome).
- `1` — workflow read successfully but the consistency checks
  surfaced one or more issues. The issues are printed in the
  `CONSISTENCY ISSUES` block of the human output or the `issues`
  array of the JSON output.
- `2` — could not read the durable state at all (DB unreachable,
  arguments missing). Triage the connection before invoking again.

When to escalate vs. self-recover:

- **Inconsistency without ongoing impact**: file a ticket with the
  full `--json` output. The coordinator self-heals on the next
  dispatch loop in most cases.
- **Inconsistency with stuck workflow** (no movement for >5 min
  after a decision should have flowed): page the on-call. The
  durable-state row may need manual repair before the workflow
  can progress.

The replay tool is **read-only**. It does not mutate Postgres and
does not re-emit decisions. A future PR may add a `--reapply` mode
that re-feeds the stored decisions through `core/dispatcher.py`
once the safety semantics are designed.
