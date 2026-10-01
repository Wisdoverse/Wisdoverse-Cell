# Wisdoverse Cell API Reference

Last updated: 2026-10-01

This page documents the current HTTP surface at a contract level. English is
the primary language for API descriptions. Response examples may include
external platform field names or fixture values when those names are part of a
real integration contract.

## Authentication

| Mechanism | Header or flow | Applies to |
|-----------|----------------|------------|
| Internal service key | `X-Internal-Key: <shared_secret>` | Agent-to-agent calls, control-plane routes, DSAR routes, detailed health/status routes |
| Control Plane operator token | `X-Control-Plane-Operator-Token: <operator_token>` | Control Plane operator routes; server configuration stores SHA-256 token hashes, actor IDs, company scopes, action scopes, and optional role IDs |
| Feishu/Lark signature | `X-Lark-Request-Timestamp`, `X-Lark-Request-Nonce`, `X-Lark-Signature` | Feishu webhook callbacks |
| WeCom signature | WeCom webhook verification fields | WeCom webhook callbacks |
| None | Not required | Basic liveness and readiness probes |

Internal key comparison must use constant-time comparison. Development
environments may skip the check only when `internal_service_key` is not
configured.

Control Plane routes resolve operator identity from server-side configuration;
request bodies cannot set the authenticated actor. Company and action scopes
are checked against the resolved resource company. In production/staging,
missing operator configuration returns `503 operator_auth_not_configured`.
Development board access is a development-only fallback.

Feishu webhook handlers must verify the raw request body before event dispatch,
card action handling, or message processing when signature verification is
enabled. Missing keys, missing headers, or mismatched signatures fail closed for
ordinary callbacks. The only exception is Feishu's encrypted URL verification
challenge: when the body contains an `encrypt` wrapper and no signature headers,
the gateway decrypts the challenge with `FEISHU_ENCRYPT_KEY` and responds with
the decrypted challenge value.

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

Services created through `create_agent_app()` return the shared structured
error envelope for `HTTPException`, request-validation failures, API-key
middleware failures, and unexpected server errors. The legacy FastAPI `detail`
field is still present while clients migrate.

```json
{
  "code": "requirement.not_found",
  "message": "Requirement not found",
  "trace_id": "trace_...",
  "timestamp": "2026-05-20T08:07:13+00:00",
  "details": null,
  "detail": "Requirement not found"
}
```

Every error response carries `X-Error-Code` and `X-Trace-ID`. Known
application errors use the namespaced values in `shared/api/errors.py`.
Unclassified `HTTPException` responses use `http.error`; unhandled server
errors use `internal.error`; validation failures use
`request.validation_failed` with `details.errors` populated.

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

### Reviewed requirement delivery API

These Requirement Manager endpoints are disabled by default:

| Method | Path | Contract |
|--------|------|----------|
| `GET` | `/api/v1/requirements/{id}/delivery-review` | Requires operator `work:execute` for the configured company; returns title, description, status, confirmer and SHA-256 `requirement_hash` for review. |
| `POST` | `/api/v1/requirements/{id}/delivery-handoff` | Requires the reviewed hash, `company_id`, positive `project_id`/`wp_id`, `goal_id`, `work_item_id`, a review `reason`, and optional `project_name`. `schema_version` is `1.0`; extra fields are rejected. |

POST uses `Idempotency-Key: requirement-delivery:{id}` and optional
`X-Trace-ID` (at most 64 characters). The server binds reviewer identity to the
operator principal, verifies company/goal/work over authenticated Control Plane
HTTP, and commits its receipt and decomposition outbox together. Repeating the
same body returns the saved receipt; changing the body or assigning another
requirement to the same company/project/work-package returns `409`.
Unconfirmed or changed snapshots also return `409`; missing requirements return
`404`; disabled configuration returns `503`. Responses use the standard error
envelope. The receipt includes `reviewed_by`, `review_reason`, `event_id`, linked
IDs and `status=queued_for_decomposition`. Existing OpenProject identifiers are
reviewed inputs; this API does not verify or create objects on that platform.
See [operations](../runbooks/roadmap-delivery-retention.md).

### Native Executor API

The optional native executor receiver is available on Requirement Manager,
PJM, Dev, and QA services. It is disabled by default with
`NATIVE_EXECUTOR_ENABLED=false`. Each runtime writes receipts only to its own
database ledger and accepts only its configured owning company.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/executor/capabilities` | Internal key | Reports runtime/company identity, enabled state, action allowlist, timeout, and fixed request/response limits |
| `POST` | `/api/v1/executor/requests` | Internal key | Executes one versioned native request and returns a durable receipt |
| `GET` | `/api/v1/executor/requests/{run_id}?company_id=...` | Internal key | Reads the receipt for a run owned by the requested company |

The version 1.0 request DTO is strict and contains `schema_version`,
`company_id`, `action`, `agent_id`, `run_id`, nullable `trace_id`, `goal_id`,
and `work_item_id`, JSON-object `input`, and bounded finite `max_cost_usd`.
Send `X-Executor-Contract: 1.0`, `X-Internal-Key`, and
`Idempotency-Key: {run_id}`. If `X-Trace-ID` is sent, it must match the body.
For `action: "wakeup"`, the runtime translates `input.action` to an
allowlisted native action. The action allowlists and operator behavior are
documented in the [native executor runbook](../runbooks/native-executor.md).
The runtime binds each run ID to the company and hash of the complete request:
an identical completed request replays its receipt, while a changed payload or
company fails closed. A `running` or `uncertain` receipt is never automatically
redispatched.

Responses use the strict `ExecutorResponse` DTO:

```json
{
  "schema_version": "1.0",
  "status": "recorded",
  "summary": "Native request recorded; business outcome acceptance is separate.",
  "cost_usd": 2.0,
  "cost_is_estimate": true,
  "output": {"native_result": {}, "executor_receipt": {}},
  "artifact_references": []
}
```

Here `cost_usd` is the reserved `max_cost_usd` ceiling, marked as an estimate;
actual usage is not metered by this receipt. `recorded` confirms only that the
native request returned and its receipt was stored. It does not mean QA,
review, or software delivery has been accepted. Input and output are capped at
1,000,000 bytes; the execution timeout defaults to 90 seconds and is
configurable from 1 to 110 seconds. A timed-out or otherwise uncertain intent
is not automatically redispatched. Reconcile it through the receipt endpoint
and the owning runtime.

The same adapter is available through `POST /agent/request` only when the
caller explicitly sends `X-Executor-Contract: 1.0`. Without that header, the
legacy generic request behavior is preserved.

## Control Plane API

Mounted at `/api/v1/control-plane` when `CONTROL_PLANE_ENABLED=true`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/companies` | List company contexts |
| `POST` | `/companies` | Create a company context |
| `GET` | `/companies/{company_id}` | Read one company context |
| `PATCH` | `/companies/{company_id}` | Update company name, mission, or metadata |
| `GET` | `/goals` | List durable company goals |
| `POST` | `/goals` | Create a goal |
| `GET` | `/goals/{goal_id}` | Read one goal |
| `PATCH` | `/goals/{goal_id}/status` | Update goal status and progress |
| `GET` | `/work-items` | List work items |
| `POST` | `/work-items` | Create a work item |
| `GET` | `/work-items/{work_item_id}` | Read one work item |
| `PATCH` | `/work-items/{work_item_id}/status` | Update work item status and owner |
| `GET` | `/work-items/{work_item_id}/activity` | Read a work-item activity feed across runs, artifacts, decisions, approvals, and audit events |
| `POST` | `/work-items/{work_item_id}/run` | Execute a work item through its owner agent or a supplied agent |
| `POST` | `/work-items/{work_item_id}/retry` | Re-run a work item through its owner agent or a supplied agent |
| `POST` | `/work-items/{work_item_id}/reassign` | Change work-item ownership without changing lifecycle status |
| `POST` | `/work-items/{work_item_id}/block` | Mark a work item blocked with a reason |
| `POST` | `/work-items/{work_item_id}/close` | Close a work item as completed, failed, or cancelled |
| `POST` | `/work-items/{work_item_id}/accept` | Record explicit reviewer acceptance/rejection of a linked artifact and latest run, with evidence hash and reason |
| `GET` | `/decisions` | List decisions |
| `POST` | `/decisions` | Create a decision |
| `GET` | `/decisions/{decision_id}` | Read one decision |
| `PATCH` | `/decisions/{decision_id}/status` | Accept, reject, or supersede a decision |
| `GET` | `/artifacts` | List artifacts |
| `POST` | `/artifacts` | Create an artifact |
| `GET` | `/artifacts/{artifact_id}` | Read one artifact |
| `GET` | `/evolution-proposals` | List self-evolution proposals |
| `POST` | `/evolution-proposals` | Create a proposal and optional technical approval |
| `GET` | `/evolution-proposals/{proposal_id}` | Read one proposal |
| `PATCH` | `/evolution-proposals/{proposal_id}/status` | Update approval or rollout state |
| `GET` | `/runs` | List agent runs |
| `GET` | `/runs/{run_id}` | Read one run |
| `GET` | `/agents` | List `AgentRole` records |
| `POST` | `/agents` | Create an `AgentRole` record |
| `GET` | `/agents/{agent_id}` | Read one agent role |
| `GET` | `/agents/{agent_id}/prompt-config` | Read the persisted system-prompt override |
| `PUT` | `/agents/{agent_id}/prompt-config` | Update the persisted system-prompt override |
| `PATCH` | `/agents/{agent_id}/status` | Change agent role status |
| `POST` | `/agents/{agent_id}/wake` | Start a manual wakeup through the configured adapter |
| `POST` | `/scheduler/heartbeats/run-once` | Run due heartbeat wakeups once |
| `GET` | `/approvals` | List approval requests |
| `POST` | `/approvals/{approval_id}/approve` | Approve one request |
| `POST` | `/approvals/{approval_id}/reject` | Reject one request |
| `GET` | `/budgets/policies` | List budget policies by scope, period, status, or scope id |
| `POST` | `/budgets/policies` | Create a budget policy |
| `GET` | `/budgets/policies/{budget_id}` | Read one budget policy |
| `PATCH` | `/budgets/policies/{budget_id}` | Update budget limit, threshold, status, model allowlist, or metadata |
| `GET` | `/budgets/usage` | List budget usage records |
| `GET` | `/audit-events` | List append-only audit events |
| `GET` | `/timeline` | Merge audit, approval, and budget evidence |
| `GET` | `/companies/{company_id}/template` | Export a portable company template with secret scrubbing |
| `POST` | `/company-templates/import` | Import a template into a company; created runtime roles begin paused pending review |
| `POST` | `/knowledge` | Register company knowledge as an existing same-company artifact URI reference |
| `POST` | `/knowledge/{knowledge_id}/publish` | Publish or revise a knowledge reference using an expected version |
| `GET` | `/knowledge/{knowledge_id}` | Read an unexpired record if caller is owner or has a granted company-local reader role |
| `DELETE` | `/knowledge/{knowledge_id}` | Owner-only deletion that writes an immutable tombstone |
| `GET` | `/audit-export` | Export redacted audit snapshots for an exact company and explicit range within the last 90 days; keyset pagination supports `after_id` and `limit` (maximum 500) |
| `POST` | `/retention` | Preview or explicitly apply bounded audit/knowledge cleanup; requires `audit:retention`, exact company, and an idempotency key for apply |
| `POST` | `/evolution-proposals/{proposal_id}/evaluations` | Create fixed-case comparative evaluation evidence |
| `GET` | `/evolution-proposals/{proposal_id}/evaluations` | Read evaluation reports for a proposal |
| `POST` | `/evolution-proposals/{proposal_id}/release` | Submit a signed release command through the native Evolution runtime; state changes are persisted only after acknowledgement |
| `POST` | `/evolution-proposals/{proposal_id}/release/reconcile` | Look up and record an existing native acknowledgement; never resubmits a missing or uncertain command |
| `POST` | `/evolution-proposals/{proposal_id}/release/recover` | Operator recovery for an expired pending command, only after authoritative receiver `404`; checks command ownership and revalidates required approval |
| `GET` | `/operating-metrics?company_id=...` | Read company-scoped operating metrics with `control-plane:read` |
| `GET` | `/operating-metrics/prometheus?company_id=...` | Render company-scoped Prometheus text exposition; omit high-cardinality identifiers as labels |

Creation endpoints validate that referenced company, goal, work item, and run
IDs belong to the same company context.

The operator token is a separate server-owned identity mechanism from the
internal service key. Missing operator configuration fails closed in staging
and production. Clients MUST NOT send `actor_id` as an authorization claim;
the authenticated principal supplies actor identity. Knowledge access also
checks owner/role ACL after company scope authorization. Same-company access
alone does not grant knowledge reads. Audit export provides a 90-day query
window. Physical audit/knowledge retention is separately disabled by default.
`POST /retention` accepts `{company_id, batch_size, dry_run}` with `batch_size`
1–1,000 and `dry_run=true` by default. Apply requires the configured feature flag
and a 1–48-character `Idempotency-Key`; changed bodies conflict, identical bodies
return the original receipt. It preserves pending messages and pinned evidence;
compact dedupe receipts and knowledge tombstones remain permanently. It does not
erase source artifacts, WAL or backups.

The evolution service exposes its native release receiver independently under
`/api/v1/evolution`: `POST /skill-releases` accepts signed deployment and
transition commands, `GET /skill-release-commands/{command_id}` retrieves the
immutable command acknowledgement, `GET /skill-releases/{deployment_id}`
reads release state, and `GET /skill-configs/{skill_id}/versions/{version}`
reads a versioned skill configuration. Control Plane release/reconcile
endpoints call this receiver over HTTP; they do not access Evolution-owned
tables.

### Governed skill execution

The optional task-time selection endpoints use the same `/api/v1/evolution`
prefix and require `X-Internal-Key`:

| Method | Path | Contract |
|--------|------|----------|
| `POST` | `/skill-executions/resolve` | Accepts frozen `company_id`, `agent_id`, `skill_id`, and task `trace_id`; returns the selected release configuration with deployment/experiment IDs, version, SHA-256 configuration hash, expiry, and HMAC signature. Returns `404` when there is no governed active/canary selection. |
| `POST` | `/skill-executions/results` | Accepts a frozen selection plus bounded score and success result; verifies selection signature/hash and records task-local evidence against the selected version. |

The feature is opt-in through `EVOLUTION_SKILL_EXECUTION_ENABLED`, default
`false`. During a traced agent task, the LLM gateway maps its requested skill
as `agent_id:task_type.replace("_", "-")`. It resolves the frozen prompt,
target model and supported parameters before budget estimation/reservation and
before calling a provider. When a governed selection is returned, model
fallback is disabled for that call so observations remain attributable to the
selected version. An unrouted task continues without a governed selection and
does not produce a live canary score.

Implementation boundaries: [`skill_execution_contract.py`](../../shared/evolution/skill_execution_contract.py),
[`skill_execution_routes.py`](../../shared/capabilities/evolution/app/skill_execution_routes.py),
[`skill_execution_store.py`](../../shared/evolution/db/skill_execution_store.py), and
[`llm_gateway.py`](../../shared/infra/llm_gateway.py).

Release reconciliation only accepts an existing receiver acknowledgement; it
does not resubmit a missing or uncertain command. The explicit `/release/recover`
path can replace a command only after it has expired and the native receiver
definitively returns `404`. A receiver acknowledgement is recorded instead of
replaced when lookup finds the prior command. Transport errors, server errors,
or other unknown outcomes do not authorize resubmission. Recovery compares the
persisted command ID and payload hash under owner locks, and rechecks the
snapshot-bound approval required for non-shadow actions.
The Control Plane implementation is in
[`evolution_releases.py`](../../shared/control_plane/api_routes/evolution_releases.py)
and [`evolution_deployment_store.py`](../../shared/control_plane/evolution_deployment_store.py).

Budget policy endpoints enforce one active policy per
`company_id + scope + scope_id + period`. Company-scoped policies must not set
`scope_id`; goal, agent, and work-item scoped policies must set it. Supported
policy statuses are `active`, `paused`, and `archived`.

The WebUI compatibility surface also exposes
`GET /api/v1/agents/{agent_id}/prompt-config` and
`PUT /api/v1/agents/{agent_id}/prompt-config` with the same response shape for
catalog-managed runtime agents such as `requirement-manager`, `pjm-agent`, and
`dev-agent`.

`AgentRole` create/list/read payloads include the event-boundary contract:
`subscribed_events` and `published_events`. These fields document how an agent
participates in EventBus communication without importing another agent's
internal implementation.

`AgentRole.status` accepts `active`, `paused`, `disabled`, `inactive`,
`retired`, and `terminated`. Only `active` roles are runnable by wakeup and
heartbeat execution; `retired` and `terminated` are terminal lifecycle states.

`agent_kind` accepts `organization_role`, `business_runtime_agent`,
`capability_module`, `integration_gateway`, and `system_worker`. Business
runtime agents are deployed root agents such as requirement manager, PJM, QA,
and Dev. Capability modules are support boundaries such as sync, analysis, and
evolution.

## Requirement Manager API

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
| `GET` | `/export/questions` | Export questions; `status=open`, `answered`, or `all` |
| `GET` | `/export/questions/download` | Download questions; `status=open`, `answered`, or `all` |
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
| `POST` | `/api/v1/pm/decompose/{wp_id}/approve` | Approve decomposition; body should include `operator` for approval evidence |
| `POST` | `/api/v1/pm/decompose/{wp_id}/reject` | Reject decomposition; body should include `operator` and may include `reason` |

Decomposition status responses use these workflow states:

| Status | Meaning |
|--------|---------|
| `pending` | Decomposition is waiting for human approval before OpenProject writes |
| `writing` | Approved decomposition is currently being written to OpenProject |
| `approved` | OpenProject write succeeded |
| `rejected` | Human rejected the proposed decomposition |
| `failed` | Decomposition generation failed before approval |
| `write_failed` | Decomposition was approved, but the OpenProject write failed |

`POST /api/v1/pm/decompose/{wp_id}/retry` is allowed only for `failed`,
`rejected`, and `write_failed` records. Event replay of
`sync.task-needs-decompose` skips `pending`, `writing`, `approved`, and
`write_failed` records to avoid duplicate OpenProject side effects.

## Chat Agent and User Interaction Gateway API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/chat-agent/requests` | Execute an internal normalized chat-agent request through the service boundary |
| `GET` | `/api/v1/chat-agent/conversation/{user_id}` | Read conversation history through the chat-agent boundary |
| `GET` | `/api/daily-progress` | List daily progress records through the chat-agent boundary |
| `POST` | `/api/bitable/confirm` | Confirm a proposed Bitable update through the chat-agent boundary |
| `POST` | `/api/bitable/reject` | Reject a proposed Bitable update through the chat-agent boundary |
| `POST` | `/api/bitable/create` | Confirm a proposed Bitable create through the chat-agent boundary |
| `POST` | `/webhook/feishu` | Receive Feishu webhook traffic |

## Analysis, Sync, Quality, Development, and Evolution APIs

| Module | Method | Path | Purpose |
|--------|--------|------|---------|
| Analysis | `POST` | `/api/v1/analysis/daily` | Generate daily report |
| Analysis | `POST` | `/api/v1/analysis/weekly` | Generate weekly report |
| Analysis | `GET` | `/api/v1/analysis/risks` | Check project risks |
| Sync | `POST` | `/api/v1/sync/trigger` | Trigger compatibility full synchronization |
| Sync | `POST` | `/api/v1/sync/openproject/trigger` | Trigger OpenProject-to-Bitable projection sync |
| Sync | `POST` | `/api/v1/sync/feishu-bitable/trigger` | Trigger Feishu Bitable-to-OpenProject progress sync |
| Sync | `GET` | `/api/v1/sync/status` | Read sync status |
| Sync | `GET` | `/api/v1/sync/mappings` | List sync mappings |
| QA | `POST` | `/api/v1/qa/run` | Start QA acceptance |
| QA | `GET` | `/api/v1/qa/runs/{run_id}` | Read one QA run |
| QA | `GET` | `/api/v1/qa/runs` | List QA runs |
| QA | `GET` | `/api/v1/qa/stats` | Read QA acceptance statistics |
| Development | `GET` | `/api/v1/dev/tasks` | List development tasks |
| Development | `GET` | `/api/v1/dev/tasks/failed` | List failed tasks |
| Development | `GET` | `/api/v1/dev/tasks/{wp_id}` | Read task detail |
| Development | `POST` | `/api/v1/dev/tasks/{task_id}/retry` | Retry task |
| Development | `POST` | `/api/v1/dev/tasks/{task_id}/cancel` | Cancel task |
| Development | `POST` | `/api/v1/dev/tasks/{task_id}/approve` | Approve task; body may include `operator` and `approval_id` for control-plane approval evidence |
| Evolution | `POST` | `/analyze` | Trigger global evolution analysis |

## Gateway and Integration APIs

| Surface | Method | Path | Purpose |
|---------|--------|------|---------|
| Rust Gateway | `GET` | `/health` | Gateway liveness |
| Rust Gateway | `GET` | `/ready` | Gateway readiness |
| Feishu integration | `POST` | `/api/feishu/webhook` | Shared Feishu webhook route |
| Feishu integration | `GET` | `/api/feishu/health` | Feishu integration health |
| WeCom integration | `GET` | `/api/wecom/webhook` | WeCom verification |
| WeCom integration | `POST` | `/api/wecom/webhook` | WeCom event callback |
| WeCom integration | `GET` | `/api/wecom/health` | WeCom integration health |
| Channel Gateway | `GET` | `/health` | Public liveness |
| Channel Gateway | `GET` | `/health/adapters` | Internal-key adapter health |
| Channel Gateway | `GET` | `/api/admin/adapters` | Internal-key adapter inventory |
| Channel Gateway | `GET` | `/api/admin/adapters/{channel_id}` | Internal-key adapter detail |

## DSAR Endpoints

Mounted by shared API helpers when enabled:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dsar/export` | Export user data |
| `POST` | `/api/dsar/delete` | Dry-run user data deletion; `confirm=true` requires an approved `approval_id` |

DSAR routes require internal authentication and must be audited. Confirmed
deletion is a legal/privacy-sensitive destructive action and must carry a
control-plane approval id when approval enforcement is enabled.

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

`POST /agent/request` accepts `X-Trace-ID`; the shared runtime copies it into
the request payload when the JSON body does not already contain `trace_id`.
