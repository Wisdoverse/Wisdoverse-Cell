# Support Capability Services

Support capability services own bounded execution workflows that are not
modeled as root business runtime agents. They are independently deployable
runtime modules used by organization-role agents, root business agents,
gateways, schedulers, or control-plane work items.

Capability packages may contain service-local API, application logic,
persistence, tests, and service-owned integrations. They must not be presented
as organization-role agents unless a durable `AgentRole` contract explicitly
defines that user-facing role.

Real business runtime agents live directly under `agents/`:
`requirement_manager/`, `pjm_agent/`, `qa_agent/`, and `dev_agent/`.

## Packages

| Package | Responsibility |
|---------|----------------|
| `sync/` | OpenProject and Feishu context synchronization. |
| `analysis/` | Risk detection and operating analytics. |
| `evolution/` | Self-evolution analysis and recommendation. |

Support capability services are `capability_module` runtime modules in the
agent catalog.
