# QA Agent

Automated acceptance verification for AI-generated code. Wisdoverse Cell's 7th agent.

Canonical agent ID: `qa-agent`.
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.5 for the bounded context catalog entry.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/qa_agent/` |
| Owned tables | `qa_acceptance_*`, `qa_agent_event_outbox` |
| Aggregate root | **None — intentional design decision (DDD-021)**. The acceptance run is a one-shot computation; outputs are immutable. See [§ Domain Model](#domain-model) below. |
| Value object | `AcceptanceVerdict` (`core/domain/acceptance_verdict.py:36-90`) — frozen dataclass with `__post_init__` validation and `is_blocking` / `is_clean` properties |
| Vocabulary | `core/domain/acceptance_vocabulary.py` — `GATE_VALUES`, `L1_STATUS_VALUES`, `FINDING_STATUS_VALUES`, `FINDING_LEVELS` constants plus `is_blocking_finding` / `is_warning_finding` helpers |
| State machine | Not modeled. An acceptance run executes once, produces one verdict, persists, and is closed. There are no in-place state transitions on a run. |
| Domain events | Published as integration events (`qa.acceptance-completed`, `qa.gate-failed`) from the use case, not raised by an aggregate. |
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

QA does not promote `AcceptanceRun` to an aggregate root with a state
machine. The decision is intentional and is recorded here per
[`ddd-compliance-audit.md`](../../docs/architecture/ddd-compliance-audit.md)
row DDD-021.

**Why not an aggregate**:

- An acceptance run is a one-shot computation. The runner produces a
  verdict in a single subprocess call; there are no in-place
  transitions on the run itself.
- Idempotency is enforced by `trigger_event_id` deduplication at the
  persistence boundary, not by aggregate invariants.
- Modeling a state machine (e.g.
  `REQUESTED → RUNNING → VERDICT_RENDERED → CLOSED`) would add
  ceremony without protecting any invariant the code does not already
  enforce — the run only progresses forward, and "in-flight" runs do
  not survive process restart (the subprocess exits or fails).

**What is modeled**:

- `AcceptanceVerdict` (value object) — owns the rules for what
  constitutes a clean, warning, or blocking outcome.
- `acceptance_vocabulary` (constants + helpers) — owns the
  classification rules (`is_blocking_finding`, `is_warning_finding`).

If QA's run flow ever grows in-place transitions (for example, a
"reviewed after the fact" status set by an operator), the decision is
to revisit and promote `AcceptanceRun` to an aggregate at that point.
Until then, the run record is a persistence DTO and the verdict is
the domain element.

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.5:

- **Upstream / downstream**: Customer/Supplier to Dev Agent (consumes `code.committed`; emits `qa.acceptance-completed` and `qa.gate-failed`).
- **Conformist** to Control Plane on AgentRun / Approval / AuditEvent Published Language.
- **Anti-Corruption Layer** pending for GitLab / OpenProject context resolution (DDD-013).


## Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `code.committed` | Subscribe | Triggers acceptance on new code |
| `qa.run-requested` | Subscribe | Manual/PJM Agent triggered run |
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
