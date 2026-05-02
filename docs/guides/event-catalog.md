# Wisdoverse Cell Event Catalog

Last updated: 2026-05-02

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
| `requirement.extracted` | requirements capability | Event observers | Requirements were extracted from source content |
| `requirement.confirmed` | requirements capability | Event observers | Requirement was confirmed |
| `requirement.rejected` | requirements capability | Event observers | Requirement was rejected |
| `requirement.changed` | requirements capability | Event observers | Requirement fields changed |
| `requirement.deleted` | requirements capability | Event observers | Requirement was deleted |
| `sync.started` | sync capability | Event observers | Synchronization started |
| `sync.completed` | sync capability | project management, analysis | Synchronization completed |
| `sync.failed` | sync capability | Event observers | Synchronization failed |
| `sync.trigger` | user interaction gateway | sync capability | User or scheduler requested sync |
| `sync.task-needs-decompose` | sync capability | project management | Synced work item needs decomposition |
| `report.daily-generated` | analysis capability | Event observers | Daily report generated |
| `report.weekly-generated` | analysis capability | Event observers | Weekly report generated |
| `analysis.risk-detected` | analysis capability | project management | Project risk detected |
| `analysis.quality-evaluated` | analysis capability | Event observers | Quality evaluation completed |
| `pm.alert-triggered` | project management | Event observers | Project-management alert created |
| `pm.decompose-completed` | project management | Event observers | Decomposition completed |
| `pm.decomposition_failed` | project management | Event observers | Decomposition failed |
| `pm.approval_timeout` | project management | Event observers | Decomposition approval timed out |
| `chat.pm-query` | user interaction gateway | project management | User asked a PM-related question |
| `chat.pm-response` | project management | user interaction gateway | PM query answer produced |
| `channel.message.inbound` | channel gateway | Event observers | External message received |
| `channel.message.outbound` | channel gateway | Event observers | External message sent |
| `channel.message.delivered` | channel gateway | Event observers | Message delivered |
| `channel.message.edited` | channel gateway | Event observers | Message edited |
| `channel.message.deleted` | channel gateway | Event observers | Message deleted |
| `channel.reaction.added` | channel gateway | Event observers | Reaction added |
| `channel.reaction.removed` | channel gateway | Event observers | Reaction removed |
| `channel.read.receipt` | channel gateway | Event observers | Read receipt received |
| `channel.adapter.status` | channel gateway | Event observers | Adapter status changed |

## 3.0 Control Plane Domain

Control-plane events connect the durable ledger with independently deployed
agents. They should include `company_id`, `trace_id`, and the most specific
available IDs among `goal_id`, `work_item_id`, and `run_id`.

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
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
| requirements capability | `requirement.*` | project/sprint/meeting events when enabled |
| sync capability | `sync.*` | scheduler/API trigger paths |
| analysis capability | `report.*`, `analysis.*` | `sync.completed` |
| project management capability | `pm.*`, `chat.pm-response` | `sync.completed`, `sync.task-needs-decompose`, `analysis.risk-detected`, `chat.pm-query` |
| user interaction gateway | `chat.pm-query`, `sync.trigger` | `chat.pm-response` |
| channel gateway | `channel.*` | adapter-specific platform callbacks |
| quality capability | `qa.*` | code or CI events when enabled |
| development capability | development workflow events | decomposed work items when enabled |
| evolution capability | `evolution.*` | execution traces and feedback |
| control plane | `goal.*`, `work_item.*`, `agent_run.*`, `audit.*` | runtime evidence and operator actions |

## 6. Evolution Events

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
| `execution.traced` | evolved-agent wrapper | evolution capability | Execution trace recorded |
| `evolution.cycle-triggered` | scheduler/API | evolution capability | Start global analysis cycle |
| `evolution.skill-proposed` | evolution capability | human review | Skill optimization proposal |
| `evolution.human-feedback` | gateway/admin UI | evolution capability | Human feedback on proposal |
| `evolution.pattern-proposed` | evolution capability | human review | Collaboration pattern proposal |
| `evolution.pattern-approved` | gateway/admin UI | evolution capability | Pattern approved |
| `evolution.pattern-shadow-complete` | shadow runner | evolution capability | Shadow run completed |

## 7. QA Events

| Event type | Producer | Consumer | Purpose |
|------------|----------|----------|---------|
| `code.committed` | CI pipeline or GitLab webhook | quality capability | Code commit available for acceptance |
| `qa.acceptance_completed` | quality capability | project management | Acceptance run completed |
| `qa.acceptance_failed` | quality capability | project management | Acceptance run failed with failure details |

## 8. Reserved Events

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

## 9. Subscription Gaps

These subscriptions exist or are planned, but producers are not fully wired yet:

| Event type | Subscriber | Status |
|------------|------------|--------|
| `project.created` | requirements capability | Planned |
| `project.updated` | requirements capability | Planned |
| `sprint.started` | requirements capability | Planned |
| `sprint.completed` | requirements capability | Planned |
| `meeting.uploaded` | requirements capability | Planned |

When implementing a reserved or gap event, update this catalog, add payload
tests, and include migration notes if any consumer behavior changes.
