# Evolution Module (`shared/capabilities/evolution`)

> Global cross-agent analysis and architecture-level optimization suggestions.

**Sibling package**: [`shared/evolution/`](../../evolution/README.md) hosts the
L1 / L2 / L3 self-evolution **runtime** (trace collector, evaluator, skill
optimizer, evolution guard, canary router, kill switch). This package
(`shared/capabilities/evolution/`) is the **L2 capability service** that
consumes that runtime: it runs cross-agent analysis cycles, produces
`EvolutionProposal` records, and surfaces approvals through the Control
Plane. The split is intentional — runtime primitives vs. capability flow.
See [DDD compliance audit row DDD-005](../../../docs/architecture/ddd-compliance-audit.md).

## Purpose

The Evolution Module is the L2 (Architecture) component of the self-evolution system. It analyzes execution traces across **all** agents to identify system-wide patterns, bottlenecks, and optimization opportunities. Unlike individual agent self-optimization (L1), this module looks at the bigger picture.

**CRITICAL**: This module must **NOT** be wrapped with `EvolvedAgent`. It uses `evolution_excluded=True` in its `create_agent_app()` call. A module that evolves itself would create a dangerous feedback loop.

---

## Bounded Context

The Evolution capability owns cross-agent analysis cycles, suggestion-mode
proposal enrichment, and approval orchestration. It does **not** own the
durable `EvolutionProposal` aggregate; that record and its rollout FSM belong
to the Control Plane ledger. This module contributes the proposal vocabulary
and immutable value objects needed to translate analysis output into the
Control Plane's published language.

## Ubiquitous Language

| Term | Meaning | Owner |
|------|---------|-------|
| Evolution proposal | A suggested L1/L2/L3 optimization emitted for human review | Control Plane aggregate; Evolution capability creates/enriches payloads |
| Evolution experiment | L1 mini-canary aggregate that routes traffic, records score evidence, and decides promote/rollback outcomes | `shared/evolution/domain/experiment.py` |
| Proposal scope | Stable target string such as `agent:pjm-agent/skill:decompose` or `pattern:handoff` | `EvolutionProposalScope` |
| Approval context | Immutable approval request, evidence, benefit, risk, metadata, and trace context derived from one proposal payload | `EvolutionProposalApprovalContext` |
| Evolution tier | L1 skill/prompt, L2 architecture, or L3 collaboration level | Control Plane `EvolutionTier`, consumed as published language |
| Proposal operation | Whitelisted operation (`add_skill`, `modify_event_subscription`, etc.) that the LLM may suggest | `EvolutionProposalOperation` |
| Rollout state | Control Plane lifecycle for a recorded proposal after approval | Control Plane `EvolutionProposal` aggregate |
| Trace evidence | Summarized execution evidence used to justify a proposal | Evolution runtime, consumed through `EvolutionTraceAnalysisStore` |
| Collaboration pattern | L3 multi-agent coordination pattern proposed in shadow/suggestion mode | `shared/evolution/collaboration` runtime, surfaced here for approval |

## Context-Map Relationships

| Neighbor | Relationship | Contract |
|----------|--------------|----------|
| Control Plane | Conformist + Customer/Supplier | Evolution conforms to `EvolutionTier`, approval status, and `EvolutionProposal` ledger semantics; Control Plane owns approvals, rollout state, and audit |
| `shared/evolution` runtime | Partnership | Runtime primitives own trace/reflection/experiment collection; this capability consumes summarized performance snapshots through ports |
| Runtime agents | Open-Host Service / Published Language | Agents expose execution traces through the evolution runtime; this capability analyzes summaries without importing agent internals |
| LLM Gateway | Anti-Corruption Layer | `GlobalAnalyzer` wraps trace data as untrusted JSON and filters responses through the domain operation whitelist |
| Human review / operator UI | Open-Host Service | `evolution.skill-proposed`, `evolution.pattern-proposed`, and Control Plane proposal records form the review contract |

---

## Events

### Subscribed

| Event | Description |
|-------|-------------|
| `evolution.cycle-triggered` | Triggers a global analysis cycle. Payload: `{"days": int}` |
| `evolution.human-feedback` | Human approval/rejection of a proposal |
| `evolution.pattern-approved` | Approval of a collaboration pattern (L3) |

### Published

| Event | Description |
|-------|-------------|
| `evolution.skill-proposed` | A skill optimization proposal for a specific agent |
| `evolution.pattern-proposed` | A new collaboration pattern proposal (L3, when enabled) |

---

## API Endpoints

All endpoints are served on the Evolution Module's default port, `8016`.
Standard health checks are provided by `create_agent_app()`.

### `GET /health`

- **Auth**: None
- **Description**: Liveness probe
- **Response**: `{"status": "alive", "agent": "evolution-module"}`

### `GET /health/ready`

- **Auth**: None
- **Description**: Readiness probe with dependency checks
- **Response**: `{"status": "ready", "checks": {...}}`

### `POST /analyze`

- **Auth**: X-Internal-Key
- **Description**: Manually trigger a global analysis cycle. Calls `GlobalAnalyzer` to scan traces from the last N days and produce optimization proposals.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int (query) | `7` | Number of days of traces to analyze |

- **Response**:
```json
{
  "proposals": [
    {
      "agent_id": "pjm-agent",
      "skill_id": "decomposition",
      "suggestion": "...",
      "evidence": ["trace_xxx", "trace_yyy"]
    }
  ]
}
```

- **Example**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  "http://localhost:8016/analyze?days=14"
```

---

## Design

### GlobalAnalyzer

The core analysis engine. It:

1. Queries execution traces across all agents from the evolution database
2. Identifies patterns: common failures, performance regressions, underperforming skills
3. Produces proposals with evidence (trace IDs) for human review

The analyzer operates with an **operation whitelist** -- it can only read traces and emit proposals. It cannot modify agent configurations directly.

### Phase 2: Suggestion Mode

Currently, the Evolution Module operates in **suggestion mode only**. All proposals require human approval before any changes are applied. The `evolution.human-feedback` event carries the approval/rejection decision.

### Phase 3: Collaboration Patterns

When `EVOLUTION_COLLABORATION_ENABLED=true`, the module also:

1. Proposes collaboration patterns from seed definitions (`collaboration/seeds.py`)
2. Processes pattern approvals via `ApprovalGateway`

---

## File Map

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry point, `/analyze` endpoint, `create_agent_app()` with `evolution_excluded=True` |
| `core/domain/proposal.py` | Immutable proposal scope, approval context, and operation whitelist value objects |
| `../../evolution/domain/experiment.py` | Runtime `EvolutionExperiment` aggregate for mini-canary promotion and rollback decisions |
| `service/agent.py` | `EvolutionModule` class -- event handling, analysis orchestration |
| `service/global_analyzer.py` | `GlobalAnalyzer` -- cross-agent trace analysis engine |
