# Agent Layout

`agents/` contains only real business runtime agents. Gateway services,
orchestration workers, and reusable support capabilities live outside this
directory.

```text
agents/
├── requirement_manager/ # Business runtime agent
├── pjm_agent/           # Business runtime agent
├── qa_agent/            # Business runtime agent
└── dev_agent/           # Business runtime agent
```

Runtime catalog metadata and organization-role templates live in
`shared/control_plane/agent_catalog.py`.

## Managed Agent Catalog

Use `get_managed_agent_catalog()` when a backend tool or UI-facing API needs a
single list of agent-like things:

| Catalog group | Runtime package | Meaning |
|---------------|-----------------|---------|
| `organization_role_template` | None | True organization role agents such as CEO, CTO, CPO, and COO. They are root catalog templates until persisted as `AgentRole` records. |
| `runtime_module` | `agents.<business_agent>`, `services.*`, or `shared.capabilities.*` | Deployed agents, gateways, workers, or support capability services. They are visible in the frontend fleet. |

This is the architecture-safe interpretation of "root agents": real business
runtime agents live directly under `agents/`, while organization-role agents
are owned by the root catalog and persisted as control-plane `AgentRole`
records.

Catalog entries use separate flags for separate concerns:

| Field | Meaning |
|-------|---------|
| `agent_kind` | Control-plane architecture kind: organization role, business runtime agent, capability module, gateway, or worker. |
| `implemented` | The package has an actual runtime implementation, not only a reserved boundary. |
| `business_agent` | The agent owns business work outcomes, not only gateway, sync, analytics, or system orchestration support. |

The implemented business runtime agents are `requirement-manager`, `pjm-agent`,
`qa-agent`, and `dev-agent`.

## Runtime Boundaries

| Path | Runtime role | Control-plane kind |
|------|--------------|--------------------|
| [`requirement_manager/`](requirement_manager/) | Requirement extraction, confirmation, PRD, and local Feishu flow | `business_runtime_agent` |
| [`pjm_agent/`](pjm_agent/) | Task decomposition, approval preparation, alerts, and reports | `business_runtime_agent` |
| [`qa_agent/`](qa_agent/) | QA acceptance and quality verification | `business_runtime_agent` |
| [`dev_agent/`](dev_agent/) | AgentForge-backed delivery execution | `business_runtime_agent` |

Non-agent runtime code lives elsewhere:

| Path | Runtime role |
|------|--------------|
| `services/gateways/user_interaction/` | User interaction and Feishu webhook gateway |
| `services/gateways/channel/` | Multi-channel messaging gateway |
| `services/orchestration/coordinator/` | Cross-service event orchestration worker |
| `shared/capabilities/sync/` | OpenProject and Feishu context sync |
| `shared/capabilities/analysis/` | Risk detection and operating analytics |
| `shared/capabilities/evolution/` | Self-evolution analysis and recommendation |

## Boundary Rules

- Add packages under `agents/` only for real business runtime agents. Do not add
  compatibility aliases or common support capabilities here.
- Agents must not import another deployed agent's internal code. Use typed HTTP
  clients or EventBus events for cross-boundary communication.
- External systems must be reached through ports, clients, or adapters.
- Service-local integrations that contain workflow logic belong under the
  owning agent. Shared platform primitives belong under `shared/integrations/`.
- Organization-role agents such as CEO, CTO, CPO, and COO are control-plane
  `AgentRole` records. They are managed from the frontend and backed by
  adapters, not by adding root-level Python packages.

## Frontend Management

The frontend manages both built-in runtime modules and control-plane role
agents through the Feature-Sliced Design agent surface:

| Frontend path | Responsibility |
|---------------|----------------|
| `frontend/src/entities/agent/` | Agent domain model, registry, API hooks, and small entity UI |
| `frontend/src/features/agent-create/` | Creates persisted `AgentRole` records |
| `frontend/src/features/agent-wakeup/` | Triggers persisted `AgentRole` wakeups |
| `frontend/src/widgets/agent-fleet/` | Fleet operator surface with kind/status/search filters |
| `frontend/src/widgets/agent-detail/` | Detail operator surface for built-ins and persisted roles |

Use `agent_kind` to distinguish runtime modules from organization-role agents:

| `agent_kind` | Meaning |
|--------------|---------|
| `organization_role` | Durable role agent record managed by the control plane |
| `business_runtime_agent` | Root deployable business agent under `agents/` |
| `capability_module` | Independently deployed capability service |
| `integration_gateway` | User-facing or platform-facing gateway service |
| `system_worker` | Internal orchestration or background worker |

Organization-role templates currently include `ceo`, `cto`, `cpo`, and `coo`.
Use `create_organization_role()` from `shared.control_plane.agent_catalog` when
backend code needs an `AgentRole` object, and use the frontend agent-create
template selector when an operator creates one manually.

## Per-Agent Shape

Use this shape for new services unless there is a specific reason to diverge:

```text
<agent>/
├── app/          # FastAPI/create_agent_app entry point and plugins
├── adapters/     # Service-local external-system clients and adapter wiring
├── api/          # HTTP routers and request/response schemas
├── core/         # Domain/application logic owned by the service
├── db/           # Persistence access for the service-owned data
├── models/       # ORM and Pydantic models owned by the service
├── service/      # BaseAgent implementation and orchestration facade
└── tests/        # Service-local unit, integration, and contract tests
```

`core/` must depend on ports or injected collaborators when it needs external
systems. HTTP clients, SDK clients, webhook clients, and provider-specific
retry/circuit-breaker code belong in `adapters/` or `shared/integrations/`,
then get wired from `service/` or `app/`.

Runtime identifiers such as `projectcell`, `project-cell`, `project_cell`,
`requirement-manager`, `chat-agent`, `pjm-agent`, `sync-module`,
`analysis-module`, `qa-agent`, `dev-agent`, and `evolution-module` are
compatibility contracts. Historical `sync-agent`, `analysis-agent`, and
`evolution-agent` identifiers are legacy aliases only; do not reintroduce them
as canonical capability names.
