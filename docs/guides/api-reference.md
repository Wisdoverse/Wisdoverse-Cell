# Wisdoverse Cell API Reference

Last updated: 2026-05-02

This page documents the current HTTP surface at a contract level. English is
the primary language for API descriptions. Response examples may include
external platform field names or fixture values when those names are part of a
real integration contract.

## Authentication

| Mechanism | Header or flow | Applies to |
|-----------|----------------|------------|
| Internal service key | `X-Internal-Key: <shared_secret>` | Agent-to-agent calls, control-plane routes, DSAR routes, detailed health/status routes |
| Feishu/Lark signature | `X-Lark-Request-Timestamp`, `X-Lark-Request-Nonce`, `X-Lark-Signature` | Feishu webhook callbacks |
| WeCom signature | WeCom webhook verification fields | WeCom webhook callbacks |
| None | Not required | Basic liveness and readiness probes |

Internal key comparison must use constant-time comparison. Development
environments may skip the check only when `internal_service_key` is not
configured.

## Common Service Endpoints

Services created through `create_agent_app()` expose:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/health` | None | Liveness probe |
| `GET` | `/health/ready` | None | Readiness probe |
| `GET` | `/health/ready/detail` | Internal key | Detailed dependency readiness |
| `GET` | `/health/startup` | None | Startup probe |
| `GET` | `/status` | Internal key | Agent runtime status |
| `POST` | `/agent/request` | Internal key | Generic request boundary for deployed agents |

`POST /agent/request` is the preferred production boundary for control-plane
wakeups. It avoids importing agent implementation code across service
boundaries.

Example request:

```json
{
  "action": "wakeup",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "input": {}
}
```

## Error Shape

FastAPI routes may return the standard `HTTPException` shape:

```json
{
  "detail": "resource not found"
}
```

Shared error middleware may wrap errors as:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "resource not found",
    "trace_id": "trace_..."
  }
}
```

Common status codes:

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Invalid request or business-rule rejection |
| `401` | Internal key authentication failed |
| `403` | Webhook signature or authorization failed |
| `404` | Resource not found |
| `500` | Internal service error |
| `502` | Upstream service error |
| `503` | Service not ready |

## Control Plane API

Mounted at `/api/v1/control-plane` when `CONTROL_PLANE_ENABLED=true`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/goals` | List durable company goals |
| `POST` | `/goals` | Create a goal |
| `GET` | `/goals/{goal_id}` | Read one goal |
| `PATCH` | `/goals/{goal_id}/status` | Update goal status and progress |
| `GET` | `/work-items` | List work items |
| `POST` | `/work-items` | Create a work item |
| `GET` | `/work-items/{work_item_id}` | Read one work item |
| `PATCH` | `/work-items/{work_item_id}/status` | Update work item status and owner |
| `GET` | `/decisions` | List decisions |
| `POST` | `/decisions` | Create a decision |
| `GET` | `/decisions/{decision_id}` | Read one decision |
| `PATCH` | `/decisions/{decision_id}/status` | Accept, reject, or supersede a decision |
| `GET` | `/artifacts` | List artifacts |
| `POST` | `/artifacts` | Create an artifact |
| `GET` | `/artifacts/{artifact_id}` | Read one artifact |
| `GET` | `/runs` | List agent runs |
| `GET` | `/runs/{run_id}` | Read one run |
| `GET` | `/agents` | List `AgentRole` records |
| `POST` | `/agents` | Create an `AgentRole` record |
| `GET` | `/agents/{agent_id}` | Read one agent role |
| `PATCH` | `/agents/{agent_id}/status` | Change agent role status |
| `POST` | `/agents/{agent_id}/wake` | Start a manual wakeup through the configured adapter |
| `POST` | `/scheduler/heartbeats/run-once` | Run due heartbeat wakeups once |
| `GET` | `/approvals` | List approval requests |
| `POST` | `/approvals/{approval_id}/approve` | Approve one request |
| `POST` | `/approvals/{approval_id}/reject` | Reject one request |
| `GET` | `/budgets/usage` | List budget usage records |
| `GET` | `/audit-events` | List append-only audit events |
| `GET` | `/timeline` | Merge audit, approval, and budget evidence |

Creation endpoints validate that referenced company, goal, work item, and run
IDs belong to the same company context.

## Requirements Capability API

Primary prefix: `/api/v1`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ingest/upload` | Ingest uploaded meeting content |
| `POST` | `/ingest/feishu` | Ingest a Feishu meeting payload |
| `GET` | `/requirements` | List requirements |
| `GET` | `/requirements/{requirement_id}` | Read one requirement |
| `PUT` | `/requirements/{requirement_id}` | Update requirement fields |
| `DELETE` | `/requirements/{requirement_id}` | Delete a requirement and related vector data |
| `GET` | `/requirements/search` | Semantic requirement search |
| `GET` | `/requirements/{requirement_id}/similar` | Find similar requirements |
| `POST` | `/requirements/check-conflict` | Classify new/update/conflict/duplicate relation |
| `PUT` | `/requirements/{requirement_id}/confirm` | Confirm a requirement |
| `PUT` | `/requirements/{requirement_id}/reject` | Reject a requirement |
| `POST` | `/requirements/batch/confirm` | Confirm multiple requirements |
| `POST` | `/requirements/batch/reject` | Reject multiple requirements |
| `POST` | `/requirements/{requirement_id}/analyze` | Analyze an existing requirement |
| `POST` | `/requirements/analyze-text` | Analyze raw requirement text |
| `GET` | `/requirements/{requirement_id}/history` | Read change history |
| `GET` | `/requirements/{requirement_id}/diff` | Compare change-history points |
| `GET` | `/requirements/{requirement_id}/context` | Read related context |
| `POST` | `/questions/{question_id}/answer` | Answer an open question |
| `GET` | `/questions/open` | List open questions |
| `GET` | `/meetings` | List ingested meetings |
| `GET` | `/stats` | Basic requirement statistics |
| `GET` | `/stats/enhanced` | Extended statistics and trend data |
| `GET` | `/export/prd` | Export PRD JSON payload |
| `GET` | `/export/prd/download` | Download generated PRD |
| `GET` | `/export/questions` | Export open questions |
| `GET` | `/export/questions/download` | Download open questions |
| `GET` | `/messages/search` | Search message/session content |
| `GET` | `/messages/session/{session_id}` | Read a message session |
| `GET` | `/admin/llm-usage` | LLM usage summary |
| `GET` | `/admin/circuit-breaker` | LLM circuit breaker state |
| `POST` | `/admin/circuit-breaker/reset` | Reset LLM circuit breaker |

## Project Management Capability API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/pm/config` | Read project-management config |
| `POST` | `/api/v1/pm/config/refresh` | Refresh config from OpenProject |
| `GET` | `/api/v1/pm/alerts` | List current alerts |
| `POST` | `/api/v1/pm/report/daily` | Trigger daily report generation |
| `POST` | `/api/v1/pm/report/weekly` | Trigger weekly report generation |
| `POST` | `/api/v1/pm/decompose/{wp_id}/retry` | Retry decomposition |
| `GET` | `/api/v1/pm/decompose/{wp_id}` | Read decomposition status |
| `POST` | `/api/v1/pm/decompose/{wp_id}/approve` | Approve decomposition |
| `POST` | `/api/v1/pm/decompose/{wp_id}/reject` | Reject decomposition |
| `POST` | `/api/v1/pm/decompose/{wp_id}/approve` | Alternate decomposition router path |
| `POST` | `/api/v1/pm/decompose/{wp_id}/reject` | Alternate decomposition router path |

## User Interaction Gateway API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/webhook/feishu` | Receive Feishu webhook traffic |
| `POST` | `/api/bitable/confirm` | Confirm a proposed Bitable update |
| `POST` | `/api/bitable/reject` | Reject a proposed Bitable update |
| `POST` | `/api/bitable/create` | Confirm a proposed Bitable create |
| `GET` | `/api/daily-progress` | List daily progress records |

## Analysis, Sync, Quality, Development, and Evolution APIs

| Module | Method | Path | Purpose |
|--------|--------|------|---------|
| Analysis | `POST` | `/api/v1/analysis/daily` | Generate daily report |
| Analysis | `POST` | `/api/v1/analysis/weekly` | Generate weekly report |
| Analysis | `GET` | `/api/v1/analysis/risks` | Check project risks |
| Sync | `POST` | `/api/v1/sync/trigger` | Trigger synchronization |
| Sync | `GET` | `/api/v1/sync/status` | Read sync status |
| Sync | `GET` | `/api/v1/sync/mappings` | List sync mappings |
| QA | `POST` | `/api/v1/qa/run` | Start QA acceptance |
| QA | `GET` | `/api/v1/qa/runs/{run_id}` | Read one QA run |
| QA | `GET` | `/api/v1/qa/runs` | List QA runs |
| QA | `GET` | `/api/v1/qa/status` | Read QA status |
| Development | `GET` | `/api/v1/dev/tasks` | List development tasks |
| Development | `GET` | `/api/v1/dev/tasks/failed` | List failed tasks |
| Development | `GET` | `/api/v1/dev/tasks/{wp_id}` | Read task detail |
| Development | `POST` | `/api/v1/dev/tasks/{task_id}/retry` | Retry task |
| Development | `POST` | `/api/v1/dev/tasks/{task_id}/cancel` | Cancel task |
| Development | `POST` | `/api/v1/dev/tasks/{task_id}/approve` | Approve task |
| Evolution | `POST` | `/analyze` | Trigger global evolution analysis |

## Gateway and Integration APIs

| Surface | Method | Path | Purpose |
|---------|--------|------|---------|
| Go Gateway | `GET` | `/health` | Gateway liveness |
| Go Gateway | `GET` | `/ready` | Gateway readiness |
| Feishu integration | `POST` | `/api/feishu/webhook` | Shared Feishu webhook route |
| Feishu integration | `GET` | `/api/feishu/health` | Feishu integration health |
| WeCom integration | `GET` | `/api/wecom/webhook` | WeCom verification |
| WeCom integration | `POST` | `/api/wecom/webhook` | WeCom event callback |
| WeCom integration | `GET` | `/api/wecom/health` | WeCom integration health |

## DSAR Endpoints

Mounted by shared API helpers when enabled:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dsar/export` | Export user data |
| `POST` | `/api/dsar/delete` | Delete user data |

DSAR routes require internal authentication and must be audited.

## A2A and MCP Protocol Routes

Wisdoverse Cell includes shared protocol route helpers:

- A2A server routes under the configured A2A prefix, including agent-card,
  task, send, and stream endpoints.
- MCP server routes under the configured MCP prefix, including initialize,
  tools, resources, prompts, and call endpoints.

These protocol routes are optional per service and should be documented in the
owning deployment manifest when enabled.

## AgentClient Pattern

Use typed clients from `shared.infra.agent_client` for synchronous inter-agent
calls. Do not import another deployable agent's Python module directly.

```python
from shared.infra.agent_client import PMAgentClient

client = PMAgentClient()
result = await client.approve_decomposition(wp_id=42, operator="alice")
```

For asynchronous collaboration, publish an EventBus event and include `trace_id`
when one already exists.
