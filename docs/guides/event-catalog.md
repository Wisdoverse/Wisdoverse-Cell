# Wisdoverse Cell Event Catalog

Last updated: 2026-05-17

This catalog documents event names, producers, consumers, and payload
expectations. English is the primary documentation language. Event names remain
stable runtime contracts and should not be renamed without a migration plan.

## 1. Event Contract

Events are immutable, fire-and-forget messages. They must carry a stable event
type, source agent, schema version, and trace context when available.

```python
Event(
    event_id="evt_{ulid}",
    event_type="{domain}.{action}",
    source_agent="agent-id",
    payload={...},
    schema_version="1.0",
)
```

Naming convention:

| Segment | Rule | Examples |
|---------|------|----------|
| `domain` | Lowercase business or platform domain | `requirement`, `sync`, `pm`, `agent_run` |
| `action` | Lowercase action, hyphenated when needed | `created`, `completed`, `risk-detected` |

Prefer past-tense actions for facts that already happened. Use command-like
actions only when the event intentionally requests work, such as `sync.trigger`.

## 2. Active Event Overview

| Event type | Producer | Consumers | Purpose |
|------------|----------|-----------|---------|
| `requirement.extracted` | requirement manager agent | Event observers | Requirements were extracted from source content |
| `requirement.confirmed` | requirement manager agent | Event observers | Requirement was confirmed |
| `requirement.rejected` | requirement manager agent | Event observers | Requirement was rejected |
| `requirement.changed` | requirement manager agent | Event observers | Requirement fields changed |
| `requirement.deleted` | requirement manager agent | Event observers | Requirement was deleted |
| `project.created` | external project system or gateway | requirement manager agent | Project context became available for requirement association |
| `project.updated` | external project system or gateway | requirement manager agent | Project context changed |
| `sprint.started` | external project system or gateway | requirement manager agent | Sprint context started |
| `sprint.completed` | external project system or gateway | requirement manager agent | Sprint context completed |
| `meeting.uploaded` | external meeting source or gateway | requirement manager agent | Meeting content is ready for requirement ingestion |
| `sync.started` | sync capability | Event observers | Synchronization started |
| `sync.completed` | sync capability | project management, analysis | Synchronization completed |
| `sync.failed` | sync capability | Event observers | Synchronization failed |
| `sync.trigger` | user interaction gateway or scheduler/API | sync capability | User or scheduler requested sync |
| `sync.task-needs-decompose` | sync capability or PJM retry path | project management | Synced work item needs decomposition |
| `report.daily-generated` | analysis capability | Event observers | Daily report generated |
| `report.weekly-generated` | analysis capability | Event observers | Weekly report generated |
| `analysis.risk-detected` | analysis capability | project management | Project risk detected |
| `analysis.quality-evaluated` | analysis capability | Event observers | Quality evaluation completed |
| `pm.alert-triggered` | project management | Event observers | Project-management alert created |
| `pm.decompose-completed` | project management | Event observers | Decomposition completed |
| `pm.decomposition-failed` | project management | Event observers | Decomposition failed |
| `pm.approval-timeout` | project management | Event observers | Decomposition approval timed out |
| `pm.prd-ready` | requirement manager or external PRD workflow | coordinator | PRD is ready for downstream decomposition planning |
| `pm.tasks-ready-for-dev` | project management or coordinator | dev agent | Decomposed tasks are ready for development |
| `chat.pm-query` | user interaction gateway | project management | User asked a PM-related question |
| `chat.pm-response` | project management | user interaction gateway | PM query answer produced |
| `coordinator.command` | user interaction gateway or control-plane API | coordinator | User or operator intent requires orchestration |
| `coordinator.response` | coordinator | user interaction gateway | Coordinator response for the requesting surface |
| `coordinator.dispatch` | coordinator | runtime agents or capability modules | Coordinator dispatched work to a target boundary |
| `task.notification` | runtime agents | coordinator | Agent task completion or failure notification |
| `task.progress` | runtime agents | coordinator | Agent progress heartbeat for long-running work |
| `a2a.task.submitted` | A2A bridge | Event observers | External A2A task was submitted |
| `a2a.task.working` | A2A bridge | Event observers | External A2A task is running |
| `a2a.task.input-required` | A2A bridge | Event observers | External A2A task requires input |
| `a2a.task.completed` | A2A bridge | Event observers | External A2A task completed |
| `a2a.task.failed` | A2A bridge | Event observers | External A2A task failed |
| `a2a.task.canceled` | A2A bridge | Event observers | External A2A task was canceled |
| `a2a.task.error` | A2A bridge | operators and Event observers | A2A routing or bridge failure occurred |
| `qa.run-requested` | dev agent or coordinator | QA agent | QA acceptance was requested for a code change |
| `qa.acceptance-completed` | QA agent | project management and dev agent | Acceptance run completed |
| `qa.gate-failed` | QA agent | project management | Acceptance gate failed with failure details |
| `dev.workflow-created` | dev agent | Event observers | AgentForge workflow was created for a task |
| `dev.mr-created` | dev agent | Event observers | Merge request was created |
| `dev.task-completed` | dev agent | Event observers | Development task completed |
| `dev.task-failed` | dev agent | Event observers | Development task failed |
| `channel.message.inbound` | channel gateway | Event observers | External message received |
| `channel.message.outbound` | agents or services | channel gateway | Request delivery to an external channel |
| `channel.message.delivered` | channel gateway | Event observers | Message delivery result recorded |
| `channel.message.edited` | channel gateway | Event observers | Message edited |
| `channel.message.deleted` | channel gateway | Event observers | Message deleted |
| `channel.reaction.added` | channel gateway | Event observers | Reaction added |
| `channel.reaction.removed` | channel gateway | Event observers | Reaction removed |
| `channel.read.receipt` | channel gateway | Event observers | Read receipt received |
| `channel.typing.started` | channel gateway | Event observers | Typing indicator started |
| `channel.adapter.status` | channel gateway | Event observers | Adapter status changed |

## 3.0 Control Plane Domain

Control-plane events connect the durable ledger with independently deployed
agents. They should include `company_id`, `trace_id`, and the most specific
available IDs among `goal_id`, `work_item_id`, and `run_id`.
Each persisted `AgentRole` should declare `subscribed_events` and
`published_events` so the control plane can review cross-agent communication
without coupling runtime packages.

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
| `company.created` | control-plane API | operator console | Company context created |
| `company.updated` | control-plane API | operator console | Company context metadata changed |
| `goal.created` | control-plane API | operator console | Durable company goal created |
| `goal.updated` | control-plane API | operator console | Goal status or progress changed |
| `work_item.created` | control-plane API | operator console | Durable work item created |
| `work_item.updated` | control-plane API | operator console | Work item status or owner changed |
| `decision.created` | control-plane API | operator console | Durable decision created |
| `decision.updated` | control-plane API | operator console | Decision status changed |
| `agent_role.created` | control-plane API | operator console | Agent role definition created |
| `agent_role.updated` | control-plane API | operator console | Agent role definition metadata or communication contract changed |
| `agent_role.status-updated` | control-plane API | operator console | Agent role status changed |
| `agent.prompt-config-updated` | control-plane API / WebUI compatibility API | operator console | Agent system-prompt override changed |
| `agent.wakeup-requested` | control-plane API | agent runtime adapter | Manual wakeup requested |
| `agent.wakeup-completed` | control-plane runner | operator console | Manual wakeup finished |
| `agent_run.started` | runtime plugin or runner | operator console | AgentRun started |
| `agent_run.succeeded` | runtime plugin or runner | operator console | AgentRun succeeded |
| `agent_run.failed` | runtime plugin or runner | operator console | AgentRun failed |
| `budget_policy.created` | control-plane API | operator console | Budget policy created |
| `budget_policy.updated` | control-plane API | operator console | Budget policy limit, status, allowlist, or metadata changed |
| `budget.usage-recorded` | BudgetGuard or LLM gateway | operator console | Budget usage appended |
| `artifact.created` | agents | operator console | Artifact produced |
| `audit.event-recorded` | control-plane ledger | operator console | Audit event appended |
| `evolution_proposal.created` | evolution capability or control-plane API | operator console | Self-evolution proposal created |
| `evolution_proposal.updated` | control-plane API or approval gate | operator console | Proposal approval or rollout state changed |
| `dlq.failed` | EventBus or agent runtime | operator console / operations | Failed or malformed event was moved to the dead letter queue |

Malformed event payloads must not be copied into `dlq.failed`. Use payload
length and a SHA-256 fingerprint for correlation instead of storing raw event
content.

Example `agent.prompt-config-updated` payload:

```json
{
  "company_id": "cmp_wisdoverse_cell",
  "agent_id": "requirement-manager",
  "updated_by": "human:operator",
  "prompt_length": 128,
  "metadata_keys": ["source"]
}
```

Example `agent.wakeup-requested` payload:

```json
{
  "company_id": "cmp_wisdoverse_cell",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "actor_id": "human:operator",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "input": {}
}
```

Example `agent_run.failed` payload:

```json
{
  "company_id": "cmp_wisdoverse_cell",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "status": "failed",
  "adapter_type": "http",
  "error_category": "network",
  "error_message": "upstream timeout"
}
```

## 3.1 Channel Gateway Domain

`channel.message.outbound` is a delivery command event. Producers publish a
`MessageOutboundPayload` with an `OutboundMessage`; `channel-gateway` resolves
the registered adapter by `message.channel_id`, calls the adapter boundary, and
publishes one `channel.message.delivered` event with a `DeliveryResult`.
Missing adapters and adapter exceptions are represented as failed delivery
results so operators can inspect the failed step without losing the event
chain.

Inbound platform state notifications such as message edits, deletes, reactions,
read receipts, and typing indicators are optional channel gateway events. They
must use the `channel.*` event names declared by the shared channel event
models, even when only a subset is implemented by a specific adapter.

Example `channel.message.outbound` payload:

```json
{
  "message": {
    "message_id": "msg_...",
    "channel_id": "feishu",
    "target_chat_id": "oc_...",
    "content": "Requirement review is ready.",
    "attachments": [],
    "reply_to_platform_message_id": null,
    "parse_mode": "plain",
    "silent": false,
    "trace_id": "trace_..."
  }
}
```

## 3.2 Requirement Context Events

`project.*`, `sprint.*`, and `meeting.uploaded` are external work-context
events consumed by the requirement manager agent. Producers may be the Rust
gateway, a platform webhook gateway, a scheduler, or another deployed service
that has crossed a documented HTTP or EventBus boundary.

The requirement manager consumes these events without importing producer
internals. `meeting.uploaded` can also be invoked through the authenticated
`POST /agent/request` boundary with `{"action": "ingest", ...}` when a
deployed caller needs synchronous ingestion.

Example `meeting.uploaded` payload:

```json
{
  "content": "Discuss login requirements and acceptance criteria.",
  "source": "feishu",
  "title": "Sprint planning",
  "meeting_date": "2026-05-03T10:30:00Z",
  "participants": ["Alice", "Bob"],
  "context": "Auth workstream",
  "source_id": "meeting_001"
}
```

Example `channel.message.delivered` payload:

```json
{
  "message_id": "msg_...",
  "channel_id": "feishu",
  "result": {
    "success": true,
    "platform_message_id": "om_...",
    "error_code": null,
    "error_message": null,
    "delivered_at": null
  }
}
```

## 3.3 Sync Capability Events

`sync.trigger` is a command event consumed by the sync runtime. Its payload may
include `scope=full`, `scope=openproject`, or `scope=feishu_bitable`; the
hyphenated alias `feishu-bitable` is accepted only for inbound compatibility.
If no scope is provided, the sync runtime runs the compatibility full sync.
The user interaction gateway exposes separate deferred tools for these
boundaries: `sync_now` emits `scope=full`, `sync_openproject` emits
`scope=openproject`, and `sync_feishu_bitable` emits `scope=feishu_bitable`.
These tool commands are staged in `chat_agent_event_outbox` before the
post-commit EventBus publish attempt. The user-interaction gateway outbox
dispatcher retries pending `sync.trigger` commands when immediate publish
fails.

`sync.started`, `sync.completed`, and `sync.failed` always include the resolved
`scope` so project-management and analysis consumers can tell whether the event
came from the full sync, the OpenProject projection, or the Feishu Bitable
progress sync.

Sync lifecycle events and OpenProject-to-PJM decomposition handoff events are
staged in `sync_agent_event_outbox` before publishing. `sync.started`,
`sync.completed`, and `sync.failed` are staged through the Sync application
service; `sync.task-needs-decompose` is staged in the OpenProject projection
transaction before the post-commit publish attempt. The Sync runtime outbox
dispatcher retries pending rows when immediate EventBus publish fails.

Example `sync.trigger` payload:

```json
{
  "triggered_by": "chat_tool",
  "scope": "openproject"
}
```

## 3.4 Analysis and Project Management Events

`analysis.quality-evaluated` carries a compact list of quality evaluation
records in `evaluations`. Analysis report/risk/quality events are staged in
`analysis_agent_event_outbox` before EventBus delivery; the runtime dispatcher
retries pending rows if the immediate post-commit publish attempt fails.
`pm.decomposition-failed` and `pm.approval-timeout` are failure-evidence events;
both should keep the workflow trace when one is available so the Coordinator and
operator surfaces can connect the failure to the original work.
`pm.tasks-ready-for-dev` is a command-style handoff to the dev agent and must
include the decomposed task list. `pm.prd-ready` is consumed by the coordinator
when an upstream PRD generation boundary has already produced the product
document.

`pm.decompose-completed` reports the current decomposition state for a work
package. Event payload `status` values are `pending`, `approved`, `rejected`,
and `write_failed`. The PJM repository also uses `writing` as an internal
persisted status while writing approved decomposition output to OpenProject.
Replayed `sync.task-needs-decompose` events must not delete or rerun records in
`pending`, `writing`, `approved`, or `write_failed`; operators retry failed
write attempts explicitly through the PJM retry API, which republishes
`sync.task-needs-decompose` after deleting the stale record.

PJM decomposition API actions that mutate local decomposition state stage their
cross-boundary events in `pjm_agent_event_outbox` in the same local transaction
before publishing. The runtime outbox dispatcher retries pending PJM events when
the broker is unavailable during the immediate post-commit publish attempt.
PJM service-level notifications that do not mutate decomposition state, such as
`pm.decomposition-failed` from orchestration exceptions and
`pm.approval-timeout` from stale approval scans, also stage events in
`pjm_agent_event_outbox` before the EventBus publish attempt.

Example `pm.decompose-completed` payload:

```json
{
  "wp_id": 12345,
  "status": "write_failed",
  "user_story_count": 0,
  "task_count": 0
}
```

Example `pm.decomposition-failed` payload:

```json
{
  "error": "LLM timeout",
  "requirement_title": "Login flow",
  "trace_id": "trace_..."
}
```

## 3.5 Coordinator, Development, and QA Events

Coordinator events are orchestration contracts, not direct package imports.
`coordinator.command` enters the coordinator boundary, `coordinator.dispatch`
routes work to a target runtime boundary, and `coordinator.response` returns a
compact response to the requesting gateway. Targeted coordinator decisions may
also emit the concrete downstream command event directly, such as
`pm.tasks-ready-for-dev` for the dev agent or `qa.run-requested` for the QA
agent. Coordinator-produced dispatch and handoff events are staged in
`coordinator_event_outbox` before EventBus delivery; the runtime dispatcher
retries pending rows if the immediate publish attempt fails. Runtime agents can
report back through `task.notification` when a dispatched task finishes or
fails, and `task.progress` during long-running work.

QA acceptance completion events are staged in `qa_agent_event_outbox` in the
same local transaction that writes `qa_acceptance_runs` and
`qa_acceptance_results`. `qa.acceptance-completed` is always staged for a
persisted run; `qa.gate-failed` is also staged when the L0 gate fails. The QA
runtime outbox dispatcher retries pending rows if immediate post-commit publish
fails.

The dev agent publishes workflow-created, merge-request-created, task-completed,
and task-failed evidence, and may request QA with `qa.run-requested` after
creating a merge request. The QA agent consumes `qa.run-requested` and
publishes acceptance facts through `qa.acceptance-completed` and
`qa.gate-failed`.

Example `qa.run-requested` payload:

```json
{
  "agent_name": "dev-agent",
  "level": "all",
  "commit_sha": "abc1234",
  "files_changed": ["agents/dev_agent/service/agent.py"],
  "mr_iid": 137,
  "gitlab_project_id": 42,
  "requested_by": "dev-agent"
}
```

Example `task.notification` payload:

```json
{
  "task_id": "task_...",
  "agent_id": "dev-agent",
  "status": "completed",
  "summary": "Merge request created",
  "result": {"mr_iid": 137},
  "usage": {"llm_tokens": 1200}
}
```

Example `task.progress` payload:

```json
{
  "task_id": "task_...",
  "agent_id": "dev-agent",
  "tool_use_count": 4,
  "llm_token_count": 3200,
  "last_activity": {"phase": "tests"},
  "recent_activities": [{"phase": "implementation"}]
}
```

## 3.6 A2A Bridge Events

The A2A bridge is a protocol adapter boundary between internal EventBus events
and external A2A agents. Internal agents must not import A2A agent
implementations directly. Route work through bridge mappings, typed HTTP/A2A
clients, or EventBus events.

When used through `handle_event()`, the bridge returns `a2a.task.*` events to
the runtime so the runtime publisher or runtime outbox owns delivery. Direct
`route_event_to_a2a()` callers must publish only through the bridge's
`EventPublisher` port.

Task state events share this payload:

```json
{
  "task_id": "task_...",
  "context_id": "trace_...",
  "status": "completed",
  "message": "Done",
  "artifacts": [
    {
      "artifact_id": "art_...",
      "name": "result.json",
      "description": "Analysis result"
    }
  ]
}
```

`a2a.task.error` uses a separate failure payload:

```json
{
  "error": "routing failed",
  "original_event_type": "requirement.extracted"
}
```

## 4. Payload Guidelines

Payloads should be small, versioned, and reconstructable from durable storage.
Do not put secrets, credentials, raw prompt text, or unredacted PII in events.

Required or recommended fields:

| Field | Requirement |
|-------|-------------|
| `company_id` | Required for control-plane events |
| `trace_id` | Required when the workflow already has one |
| `goal_id` | Recommended when the event advances goal work |
| `work_item_id` | Recommended when the event advances a durable work item |
| `run_id` | Recommended for runtime execution evidence |
| `schema_version` | Required on the Event object |

## 4.1 Idempotency Contract

EventBus delivery is at-least-once. Every consumer MUST be idempotent.
Two keys are involved:

1. **`event_id`** (envelope key). Stable per published event with the
   `evt_` prefix; generated by the producer from
   `shared.core.ids.generate_id(IDPrefix.EVENT)`. A replay of the same
   `event_id` is a no-op for the consumer.
2. **Domain idempotency key** (payload field). The natural business
   identifier that lets the consumer say "I have already applied
   this." Required when the event drives a mutation in the consumer's
   own durable state.

Per-event domain idempotency keys (target contract):

| Event type | Domain idempotency key | Consumer-side check |
|------------|------------------------|---------------------|
| `requirement.extracted` | `requirement_id` | Refuse insert if record exists |
| `requirement.confirmed` | `requirement_id` | Read-then-write; transition through aggregate (`Requirement.transition_to(CONFIRMED)`) |
| `requirement.rejected` | `requirement_id` | Same as above |
| `requirement.updated` | `requirement_id` + `change_set_hash` | Skip if hash already recorded |
| `sync.completed` | `sync_run_id` | Skip if a sync row exists with that id |
| `sync.task-needs-decompose` | `work_item_id` | Trigger only if no decomposition row exists for `(work_item_id, status=pending)` |
| `pm.decompose-completed` | `wp_id` | Aggregate `Decomposition.transition_to(...)` rejects illegal moves |
| `pm.decomposition-failed` | `wp_id` | Same |
| `pm.tasks-ready-for-dev` | `task_id` per task | Dev agent skips if task row exists |
| `dev.workflow-created` | `task_id` | QA skips if acceptance run already exists for the task |
| `dev.task-completed` | `task_id` | Aggregate `Task.transition_to(COMPLETED)` rejects illegal moves |
| `dev.task-failed` | `task_id` | Aggregate `Task.transition_to(FAILED)` rejects illegal moves |
| `qa.run-requested` | `trigger_event_id` | QA store has `get_by_trigger_event_id` |
| `qa.acceptance-completed` | `run_id` | Consumer reads run record; idempotent verdict propagation |
| `qa.gate-failed` | `run_id` | Same |
| `agent_run.started` / `.succeeded` / `.failed` | `run_id` | `AgentRunLifecycle.transition_to(...)` rejects illegal moves |
| `approval.requested` / `.approved` / `.rejected` | `approval_id` | Resolve once; subsequent resolves are no-ops |
| `evolution.proposal-emitted` | `proposal_id` | Proposal store deduplicates |
| `chat.pm-query` | `message_id` | Gateway dedupes by inbound message id |
| `coordinator.dispatch` | `event_id` (no domain key) | Coordinator state-store records processed event_ids |

Rules:

- A new event MUST declare its idempotency key in the catalog row in
  the same PR that introduces it.
- A consumer that cannot apply the natural domain key MUST fall back
  to the envelope `event_id`. State-store-based dedup is allowed for
  coordination events that do not mutate business records.
- Replays from `dlq.failed` MUST be re-checked against the
  idempotency key; the architecture-principle is that a replay
  produces no second side-effect.

See [`docs/architecture/event-guidelines.md`](../architecture/event-guidelines.md)
§5 for the broader idempotency policy and
[`docs/architecture/observability-guidelines.md`](../architecture/observability-guidelines.md)
§6 for the DLQ alert that fires when consumers cannot apply the key.

## 5. Producer and Consumer Matrix

| Agent/module | Publishes | Subscribes |
|--------------|-----------|------------|
| requirement manager agent | `requirement.*` | `project.*`, `sprint.*`, `meeting.uploaded`, `coordinator.dispatch` |
| sync runtime | `sync.*` with `scope=full`, `openproject`, or `feishu_bitable` | `sync.trigger`, scheduler/API trigger paths |
| analysis capability | `report.*`, `analysis.*` via `analysis_agent_event_outbox` | `sync.completed` |
| PJM agent | `pm.*`, `chat.pm-response`, retry `sync.task-needs-decompose` | `sync.completed`, `sync.task-needs-decompose`, `analysis.risk-detected`, `chat.pm-query`, `coordinator.dispatch` |
| user interaction gateway | `chat.pm-query`, `coordinator.command`, `sync.trigger` via `chat_agent_event_outbox` | `chat.pm-response`, `coordinator.response` |
| coordinator | `coordinator.response`, `coordinator.dispatch`, `pm.tasks-ready-for-dev`, `qa.run-requested` via `coordinator_event_outbox` | `coordinator.command`, `task.notification`, `task.progress`, `pm.prd-ready`, `pm.decompose-completed`, `pm.decomposition-failed`, `analysis.risk-detected` |
| channel gateway | `channel.message.inbound`, `channel.message.delivered`, `channel.message.edited`, `channel.message.deleted`, `channel.reaction.added`, `channel.reaction.removed`, `channel.read.receipt`, `channel.typing.started`, `channel.adapter.status` via `channel_gateway_event_outbox` | `channel.message.outbound`, adapter-specific platform callbacks |
| QA agent | `qa.acceptance-completed`, `qa.gate-failed` | `code.committed`, `qa.run-requested` |
| Dev agent | `dev.workflow-created`, `dev.mr-created`, `dev.task-completed`, `dev.task-failed`, `qa.run-requested` via `dev_agent_event_outbox` | `pm.tasks-ready-for-dev`, `qa.acceptance-completed` |
| A2A bridge | `a2a.task.*` | mapped EventBus events |
| evolution capability | `evolution.*` via `evolution_event_outbox` | `evolution.cycle-triggered`, `evolution.human-feedback`, `evolution.pattern-approved`; reads persisted execution traces |
| control plane | `goal.*`, `work_item.*`, `agent_run.*`, `audit.*` | runtime evidence and operator actions |

## 6. Evolution Events

Execution traces are currently persisted by the runtime wrapper and read by the
evolution capability from storage. Do not document `execution.traced` as an
active EventBus contract until a publisher and consumer are wired.
Evolution proposal events are staged in `evolution_event_outbox` before EventBus
delivery; the runtime dispatcher retries pending rows if the immediate publish
attempt fails.

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
| `evolution.cycle-triggered` | scheduler/API | evolution capability | Start global analysis cycle |
| `evolution.skill-proposed` | evolution capability | human review | Skill optimization proposal; include `control_plane_proposal_id` when the control-plane ledger is enabled |
| `evolution.human-feedback` | gateway/admin UI | evolution capability | Human feedback on proposal; include `user_id` or `resolved_by` when an approval id is present |
| `evolution.pattern-proposed` | evolution capability | human review | Collaboration pattern proposal; include `control_plane_proposal_id` when the control-plane ledger is enabled |
| `evolution.pattern-approved` | gateway/admin UI | evolution capability | Pattern approved; include `user_id` when an approval id is present |

## 7. QA Events

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
| `code.committed` | CI pipeline or GitLab webhook | QA agent | Code commit available for acceptance |
| `qa.run-requested` | dev agent or coordinator | QA agent | Acceptance run requested |
| `qa.acceptance-completed` | QA agent | project management and dev agent | Acceptance run completed |
| `qa.gate-failed` | QA agent | project management | Acceptance gate failed with failure details |

## 8. Dev Agent Events

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
| `pm.tasks-ready-for-dev` | PJM agent or coordinator | Dev agent | Development tasks are ready for execution |
| `dev.workflow-created` | Dev agent | Event observers | AgentForge workflow was created |
| `dev.mr-created` | Dev agent | Event observers | Merge request was created |
| `dev.task-completed` | Dev agent | Event observers | Development task completed after QA |
| `dev.task-failed` | Dev agent | Event observers | Development task failed |

Dev result-collection events are staged in `dev_agent_event_outbox` in the same
local transaction that updates the Dev task and workflow log, then published
after commit. The Dev runtime outbox dispatcher retries pending rows if the
immediate post-commit EventBus publish fails.

## 9. Reserved Events

These names are reserved for future implementation. Do not reuse them for a
different meaning.

| Domain | Event types |
|--------|-------------|
| `code` | `code.reviewed` |
| `feature` | `feature.completed` |
| `test` | `test.passed`, `test.failed` |
| `deployment` | `deployment.started`, `deployment.completed` |
| `device` | `device.online`, `device.offline`, `device.alert` |
| `lead` | `lead.qualified` |
| `deal` | `deal.won` |
| `ticket` | `ticket.created` |
| `approval` | `approval.requested`, `approval.granted`, `approval.rejected` |
| `evolution` | `execution.traced`, `evolution.pattern-shadow-complete` |
| `dev` | `dev.workflow-completed` |

## 10. External Producer Boundaries

These events are consumed by the repository runtime, but their producers are
external systems, gateways, schedulers, or deployment-specific integration
services. Wire producers only through HTTP or EventBus boundaries.

| Event type | Subscriber | Status |
|------------|------------|--------|
| `project.created` | requirement manager agent | Consumer implemented; producer is external or deployment-specific |
| `project.updated` | requirement manager agent | Consumer implemented; producer is external or deployment-specific |
| `sprint.started` | requirement manager agent | Consumer implemented; producer is external or deployment-specific |
| `sprint.completed` | requirement manager agent | Consumer implemented; producer is external or deployment-specific |
| `meeting.uploaded` | requirement manager agent | Consumer implemented; can also use `/agent/request` ingest |
| `pm.prd-ready` | coordinator | Consumer implemented; producer is a PRD generation boundary or deployment-specific workflow |

When implementing a new producer for these events, update this catalog, add
payload tests, and include migration notes if consumer behavior changes.
