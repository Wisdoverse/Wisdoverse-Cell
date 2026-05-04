# Wisdoverse Cell Event Catalog

Last updated: 2026-05-04

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
| `agent_role.status-updated` | control-plane API | operator console | Agent role status changed |
| `agent.wakeup-requested` | control-plane API | agent runtime adapter | Manual wakeup requested |
| `agent.wakeup-completed` | control-plane runner | operator console | Manual wakeup finished |
| `agent_run.started` | runtime plugin or runner | operator console | AgentRun started |
| `agent_run.succeeded` | runtime plugin or runner | operator console | AgentRun succeeded |
| `agent_run.failed` | runtime plugin or runner | operator console | AgentRun failed |
| `budget.usage-recorded` | BudgetGuard or LLM gateway | operator console | Budget usage appended |
| `artifact.created` | agents | operator console | Artifact produced |
| `audit.event-recorded` | control-plane ledger | operator console | Audit event appended |
| `evolution_proposal.created` | evolution capability or control-plane API | operator console | Self-evolution proposal created |
| `evolution_proposal.updated` | control-plane API or approval gate | operator console | Proposal approval or rollout state changed |
| `dlq.failed` | EventBus or agent runtime | operator console / operations | Failed or malformed event was moved to the dead letter queue |

Malformed event payloads must not be copied into `dlq.failed`. Use payload
length and a SHA-256 fingerprint for correlation instead of storing raw event
content.

Example `agent.wakeup-requested` payload:

```json
{
  "company_id": "cmp_projectcell",
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
  "company_id": "cmp_projectcell",
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
events consumed by the requirement manager agent. Producers may be the Go
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

`sync.started`, `sync.completed`, and `sync.failed` always include the resolved
`scope` so project-management and analysis consumers can tell whether the event
came from the full sync, the OpenProject projection, or the Feishu Bitable
progress sync.

Example `sync.trigger` payload:

```json
{
  "triggered_by": "chat_tool",
  "scope": "openproject"
}
```

## 3.4 Analysis and Project Management Events

`analysis.quality-evaluated` carries a compact list of quality evaluation
records in `evaluations`. `pm.decomposition-failed` and `pm.approval-timeout`
are failure-evidence events; both should keep the workflow trace when one is
available so the Coordinator and operator surfaces can connect the failure to
the original work. `pm.tasks-ready-for-dev` is a command-style handoff to the
dev agent and must include the decomposed task list. `pm.prd-ready` is consumed
by the coordinator when an upstream PRD generation boundary has already produced
the product document.

`pm.decompose-completed` reports the current decomposition state for a work
package. Event payload `status` values are `pending`, `approved`, `rejected`,
and `write_failed`. The PJM repository also uses `writing` as an internal
persisted status while writing approved decomposition output to OpenProject.
Replayed `sync.task-needs-decompose` events must not delete or rerun records in
`pending`, `writing`, `approved`, or `write_failed`; operators retry failed
write attempts explicitly through the PJM retry API, which republishes
`sync.task-needs-decompose` after deleting the stale record.

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
agent. Runtime agents can report back through `task.notification` when a
dispatched task finishes or fails, and `task.progress` during long-running work.

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

## 5. Producer and Consumer Matrix

| Agent/module | Publishes | Subscribes |
|--------------|-----------|------------|
| requirement manager agent | `requirement.*` | `project.*`, `sprint.*`, `meeting.uploaded`, `coordinator.dispatch` |
| sync runtime | `sync.*` with `scope=full`, `openproject`, or `feishu_bitable` | `sync.trigger`, scheduler/API trigger paths |
| analysis capability | `report.*`, `analysis.*` | `sync.completed` |
| PJM agent | `pm.*`, `chat.pm-response`, retry `sync.task-needs-decompose` | `sync.completed`, `sync.task-needs-decompose`, `analysis.risk-detected`, `chat.pm-query`, `coordinator.dispatch` |
| user interaction gateway | `chat.pm-query`, `coordinator.command`, `sync.trigger` | `chat.pm-response`, `coordinator.response` |
| coordinator | `coordinator.response`, `coordinator.dispatch`, `pm.tasks-ready-for-dev`, `qa.run-requested` | `coordinator.command`, `task.notification`, `task.progress`, `pm.prd-ready`, `pm.decompose-completed`, `pm.decomposition-failed`, `analysis.risk-detected` |
| channel gateway | `channel.message.inbound`, `channel.message.delivered`, `channel.message.edited`, `channel.message.deleted`, `channel.reaction.added`, `channel.reaction.removed`, `channel.read.receipt`, `channel.typing.started`, `channel.adapter.status` | `channel.message.outbound`, adapter-specific platform callbacks |
| QA agent | `qa.acceptance-completed`, `qa.gate-failed` | `code.committed`, `qa.run-requested` |
| Dev agent | `dev.workflow-created`, `dev.mr-created`, `dev.task-completed`, `dev.task-failed`, `qa.run-requested` | `pm.tasks-ready-for-dev`, `qa.acceptance-completed` |
| A2A bridge | `a2a.task.*` | mapped EventBus events |
| evolution capability | `evolution.*` | `evolution.cycle-triggered`, `evolution.human-feedback`, `evolution.pattern-approved`; reads persisted execution traces |
| control plane | `goal.*`, `work_item.*`, `agent_run.*`, `audit.*` | runtime evidence and operator actions |

## 6. Evolution Events

Execution traces are currently persisted by the runtime wrapper and read by the
evolution capability from storage. Do not document `execution.traced` as an
active EventBus contract until a publisher and consumer are wired.

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
