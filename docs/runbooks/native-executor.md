# Native executor runbook

This runbook describes the owner-local native executor boundary for the
Requirement Manager, PJM, Dev, and QA runtimes. It is an implementation
reference; enabling the endpoint does not establish production readiness or a
live platform pilot.

## Enablement and ownership

`NATIVE_EXECUTOR_ENABLED` is off by default. Leave it off until the runtime
schema is migrated, the internal network and credentials are configured, and
the owning service's action allowlist has been reviewed. The default request
timeout is 90 seconds and is configurable from 1 to 110 seconds.

Each runtime owns its own receipt ledger and session. The table names are
`requirement_manager_executor_requests`, `pjm_executor_requests`,
`dev_agent_executor_requests`, and `qa_executor_requests`. Requests must use
the owning runtime's configured company ID; the current default is
`cmp_wisdoverse_cell`. The executor does not connect to another runtime's
database. Apply the normal Alembic migration before enabling the feature; the
development-only table initializer is not a deployment migration.

The runtime exposes:

- `GET /api/v1/executor/capabilities`
- `POST /api/v1/executor/requests`
- `GET /api/v1/executor/requests/{run_id}?company_id={company_id}`

All three endpoints require `X-Internal-Key`. Keep that key in the secret
manager and send it only over the private service network. The POST also
requires `X-Executor-Contract: 1.0` and `Idempotency-Key` equal to the body
`run_id`. If supplied, `X-Trace-ID` must exactly match the body's `trace_id`.
The receiver rejects mismatches and requests for another owning company.

## Request and native action translation

The version 1.0 request is a strict JSON object:

```json
{
  "schema_version": "1.0",
  "company_id": "cmp_wisdoverse_cell",
  "action": "wakeup",
  "agent_id": "requirement-manager",
  "run_id": "run_01J...",
  "trace_id": "trace_01J...",
  "goal_id": null,
  "work_item_id": null,
  "input": {"action": "ingest", "content": "..."},
  "max_cost_usd": 2.0
}
```

For `action: "wakeup"`, the native action is `input.action`; for other
supported top-level actions, the top-level action is passed through. The
selected action must be in the runtime's fixed allowlist. A conflicting
`input.action`, an executor-owned `_executor_context` field, or a trace ID in
`input` that conflicts with the envelope is rejected. The runtime adds its
trusted executor context and trace ID before calling its own
`handle_request()` implementation.

The current action allowlists are deliberately narrow:

| Runtime | Actions |
| --- | --- |
| Requirement Manager | `ingest` |
| PJM | `config`, `get_decompose`, `retry_decompose` |
| Dev | `get_task_status`, `list_active_workflows`, `list_failed`, `retry_task`, `cancel_workflow`, `approve_workflow` |
| QA | `run`, `list_runs`, `get_run`, `stats` |

Use each runtime's established native input fields for the selected action.
For example, Requirement Manager `ingest` takes `content` and optional
`source`, `title`, `meeting_date`, `participants`, `context`, and `source_id`;
QA `run` takes `agent_name`, optional `level`, `commit_sha`,
`mr_iid`, `gitlab_project_id`, and `requested_by`. See the owning
runtime request use cases for the complete action contract.

The request body is limited to 1,000,000 bytes. Native handler output must be a
JSON object and the serialized executor response is limited to 1,000,000
bytes. Execution is bounded by the configured timeout. A handler exception,
timeout, cancellation, or receipt persistence failure can occur after business
effects; the adapter marks the committed intent uncertain when possible and
returns an uncertain-effects error.

## Receipts, replay, and outcome meaning

The ledger commits a `running` intent before invoking the native handler. A
matching completed request replays its saved response. Reusing a `run_id` with
a different request hash or company is rejected. A duplicate whose prior
intent is still `running` or `uncertain` fails closed; the handler is never
automatically retried. Operators can inspect the owner-local receipt endpoint
to distinguish `running`, `uncertain`, and completed states. Reconcile any
uncertain business effects through the owning runtime before deciding on a new
run ID.

Successful handling returns status `recorded`, with the native result nested
under `output.native_result` and the executor context under
`output.executor_receipt`. This means the native request was recorded and
returned a response. It does **not** mean software delivery was accepted or
that a business outcome passed its acceptance gate. Control Plane acceptance
and human review remain separate.

`max_cost_usd` is a reserved ceiling supplied with the request. The response
returns that ceiling as `cost_usd` with `cost_is_estimate: true`; this ledger
does not meter actual runtime cost. Treat it as a conservative reservation,
not observed spend.

## Delivery boundary and current gap

The existing native flow can receive independently owned HTTP requests and
the runtime events already in the event catalog. There is still no validated
mapping from a confirmed Requirement to an OpenProject work package and PJM
decomposition request. Requirement confirmation alone does not provide the
OpenProject project/work-package identity and delivery context PJM needs.
Keep that mapping as explicit integration work; do not treat a `recorded`
receipt, this runbook, or an enabled endpoint as evidence of a completed
Requirement-to-delivery flow or a live platform pilot.

## Migration and rollback

The migration `20261001_native_executor_receipts` creates all four owner-local
ledger tables. Its downgrade refuses to drop any nonempty ledger because those
intents prevent old run IDs from reopening possible business effects. Do not
clear these tables as a routine rollback step.

To roll back the feature, set `NATIVE_EXECUTOR_ENABLED=false` and redeploy the
runtime. Keep the ledger tables and their rows so operators retain the replay
and reconciliation record. Only consider schema downgrade after a separately
reviewed purge and verified empty ledgers.

Dev S4.1's historical migration and restore proof covered its then-current
three-table cutover. The executor receipt ledger is additional state and that
evidence does not cover it. Any deployment with the native executor enabled
must include the new ledger table in its backup, restore, cutover, and rollback
scope. Do not cite S4.1 as proof of this ledger's recovery behavior.
