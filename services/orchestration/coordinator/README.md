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
| Owned tables | `coordinator_event_outbox` (durable); scratchpad + agent-state via port-backed adapters |
| Aggregate root | Not yet promoted (`Decision`, `WorkflowState`, `DecisionRecord` are Pydantic records). |
| ACL ports | `core/event_use_cases.py` `CoordinatorThinkerPort` (LLM thinker — DDD-019 landed) |
| State store | `core/state_ports.py` `CoordinatorStateStorePort` Protocol; default `db/state_store.py` adapter is **in-memory** — DDD-018 introduces a durable adapter. |
| Scratchpad | `core/event_use_cases.py` `CoordinatorScratchpadPort` Protocol; durable backing TBD per DDD-018. |
| Domain events | Inbound classified via `core/classifier.py`; outbound decisions mapped to events via `core/dispatcher.py` `decision_to_event()`. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Classified event** | An inbound EventBus event tagged with a `kind` (e.g. `progress`, `chat`, `coordinator-dispatch`) by `classifier.py`. |
| **Decision** | A typed instruction the coordinator emits for downstream agents (e.g. "Dev should start task X"). Drained from the LLM thinker. |
| **Scratchpad** | The short-term reasoning context the coordinator presents to the thinker (incremental view that can be compacted on growth). |
| **Agent state** | Per-agent runtime status (working / idle / current-task) cached by the coordinator for use in the next thinker context. |
| **Thinker** | The LLM-backed planner. Behind `CoordinatorThinkerPort` (DDD-019). |
| **Dispatch envelope** | The wrapper event the coordinator emits to deliver a Decision to a target agent. |

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
  classifier.py             inbound event → ClassifiedEvent
  dispatcher.py             Decision → dispatch event
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
