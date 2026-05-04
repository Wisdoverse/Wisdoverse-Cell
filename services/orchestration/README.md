# Orchestration Agents

Orchestration agents coordinate work across runtime modules. They route events,
maintain collaboration flow, and call other agents only through HTTP typed
clients or EventBus contracts.

Orchestration packages must not import gateway or capability internals. Shared
contracts should live in `shared/core`, `shared/protocols`, API docs, or the
Event Catalog.

## Packages

| Package | Responsibility |
|---------|----------------|
| `coordinator/` | Cross-module event orchestration worker. |

Orchestration agents are `system_worker` runtime modules in the agent catalog.
