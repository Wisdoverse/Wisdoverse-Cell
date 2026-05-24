# QA Agent

Automated acceptance verification for AI-generated code. Wisdoverse Cell's 7th agent.

Canonical agent ID: `qa-agent`.
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.5 for the bounded context catalog entry.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/qa_agent/` |
| Owned tables | `qa_acceptance_*`, `qa_agent_event_outbox` |
| Aggregate root | `AcceptanceRun` (`core/domain/acceptance_run.py`) — requested/running/completed lifecycle aggregate with completion invariants and `AcceptanceRunCompleted` domain event |
| Value object | `AcceptanceVerdict` (`core/domain/acceptance_verdict.py`) — frozen dataclass with `__post_init__` validation, `from_summary()`, and `is_blocking` / `is_clean` properties |
| Vocabulary | `core/domain/acceptance_vocabulary.py` wraps the shared Published Language in `shared/core/qa_acceptance.py` with QA-domain names: `GATE_VALUES`, `L1_STATUS_VALUES`, `L2_STATUS_VALUES`, `FINDING_STATUS_VALUES`, `FINDING_LEVELS` plus gate/finding classification helpers |
| State machine | `AcceptanceRunStatus` models requested → running → completed transitions. The runtime still persists the completed projection only until QA needs durable in-flight runs. |
| Domain events | `AcceptanceRunCompleted` raised by the aggregate and translated to `qa.acceptance-completed` / `qa.gate-failed` integration events by the application use case. |
| ACL | `adapters/acceptance_request_acl.py` translates `code.committed` and `qa.run-requested` payloads into QA-local `QAAcceptanceRequestEnvelope`, `QARunRequest`, `GitLabMergeRequestContext`, and optional `OpenProjectWorkPackageContext` |
| Unit of work | `core/unit_of_work_ports.py` `QAUnitOfWorkFactory` |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Acceptance Run** | One execution of the acceptance framework against a specific target (`agent_name`, optional `mr_iid`, optional `diff_ref`). Triggered by `code.committed` or `qa.run-requested`. Identified by a `run_id`. |
| **Verdict** | The immutable outcome of an acceptance run, captured as the `AcceptanceVerdict` value object. Combines `l0_gate`, `l1_status`, `l2_status` outcomes. |
| **L0 / L1 / L2** | Acceptance check tiers. L0 is the merge-blocking gate; L1 is the warning band; L2 is informational. |
| **Gate** | The L0 decision (`PASS` / `FAIL` / `ERROR`) that determines whether the run blocks a merge request. |
| **Finding** | One observation produced by an acceptance check. Has `level`, `category`, `check`, `status`, optional `details` / `file` / `line` / `severity`. |
| **Blocking finding** | A finding whose `(level, status)` combination would fail the L0 gate. See `is_blocking_finding` in `acceptance_vocabulary.py`. |
| **Idempotency key** | A `trigger_event_id` recorded on the persisted run so a re-delivered trigger event does not produce a duplicate run. |

Cross-link to the company-wide vocabulary:
[`docs/overview/glossary.md`](../../docs/overview/glossary.md).

## Domain Model

QA models `AcceptanceRun` as the aggregate root for the run lifecycle.
The aggregate owns requested → running → completed transitions,
completion invariants, `AcceptanceRunCompleted`, and the event buffer
drained before the application layer stages `qa.acceptance-completed` /
`qa.gate-failed` integration events. The synchronous runner still
persists only the completed projection, but the application must create
the aggregate and its events before writing the database row.

**What is modeled**:

- `AcceptanceRun` (aggregate) — owns `run_id` identity, target shape,
  lifecycle transitions, non-negative counts/duration, blocking-finding
  selection, and the completion event buffer.
- `AcceptanceVerdict` (value object) — owns the rules for what
  constitutes a clean, warning, or blocking outcome.
- `acceptance_vocabulary` (constants + helpers) — wraps the shared
  QA acceptance Published Language and owns the QA-domain names for
  classification rules (`is_failing_gate`, `is_blocking_finding`,
  `is_warning_finding`, `is_informational_finding`).
- `QAAcceptanceRequestACL` (adapter ACL) — translates inbound
  source-system event payloads into QA-local request/context objects
  before core event use cases run acceptance.

If QA's run flow grows in-place transitions, the aggregate should be
extended with an explicit requested/running/completed state machine.

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.5:

- **Upstream / downstream**: Customer/Supplier to Dev Agent (consumes `code.committed`; emits `qa.acceptance-completed` and `qa.gate-failed`).
- **Conformist** to Control Plane on AgentRun / Approval / AuditEvent Published Language.
- **Anti-Corruption Layer** to GitLab / OpenProject context via `adapters/acceptance_request_acl.py`.


## Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `code.committed` | Subscribe | Triggers acceptance on new code |
| `qa.run-requested` | Subscribe | Manual/Dev Agent triggered run |
| `qa.acceptance-completed` | Publish | Always — full report |
| `qa.gate-failed` | Publish | Only on L0 FAIL |

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/qa/run` | POST | Trigger acceptance run |
| `/api/v1/qa/runs` | GET | List run history |
| `/api/v1/qa/runs/{id}` | GET | Run detail |
| `/api/v1/qa/stats` | GET | Aggregated stats |
| `/health` | GET | Liveness |
| `/health/ready` | GET | Readiness |
| `/metrics` | GET | Prometheus |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `GITLAB_API_URL` | - | GitLab API base URL |
| `GITLAB_PROJECT_ID` | - | GitLab project ID |
| `GITLAB_QA_TOKEN` | - | Bot token for MR comments |
| `QA_RUNNER_TIMEOUT_SECONDS` | 120 | Runner subprocess timeout |
| `QA_FEISHU_WEBHOOK_URL` | - | QA-specific Feishu webhook |
| `QA_HIGH_SEVERITY_CHECKS` | - | Comma-separated L1 checks that trigger Feishu |

## Development

```bash
# Run locally
make qa-dev  # uvicorn --reload on port 8014

# Run tests
pytest agents/qa_agent/tests/ -v

# Self-acceptance
python .acceptance/runner.py --target agents/qa_agent --level all
```

## Architecture

```
code.committed → QAAgent.handle_event()
                      ↓
              AcceptanceRunnerService (subprocess: .acceptance/runner.py)
                      ↓
              QAReportStore (persist to PostgreSQL)
                      ↓
              QANotifier (EventBus + Feishu + GitLab MR)
```

Port: 8014 | Redis DB: 5
