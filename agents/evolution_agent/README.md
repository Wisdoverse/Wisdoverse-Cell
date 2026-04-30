# Evolution Agent (`agents/evolution_agent`)

> Global cross-agent analysis and architecture-level optimization suggestions.

## Purpose

The Evolution Agent is the L2 (Architecture) component of the self-evolution system. It analyzes execution traces across **all** agents to identify system-wide patterns, bottlenecks, and optimization opportunities. Unlike individual agent self-optimization (L1), this agent looks at the bigger picture.

**CRITICAL**: This agent must **NOT** be wrapped with `EvolvedAgent`. It uses `evolution_excluded=True` in its `create_agent_app()` call. An evolution agent that evolves itself would create a dangerous feedback loop.

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

All endpoints are served on the Evolution Agent's port. Standard health checks are provided by `create_agent_app()`.

### `GET /health`

- **Auth**: None
- **Description**: Liveness probe
- **Response**: `{"status": "alive", "agent": "evolution-agent"}`

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
  "http://localhost:<port>/analyze?days=14"
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

Currently, the Evolution Agent operates in **suggestion mode only**. All proposals require human approval before any changes are applied. The `evolution.human-feedback` event carries the approval/rejection decision.

### Phase 3: Collaboration Patterns

When `EVOLUTION_COLLABORATION_ENABLED=true`, the agent also:

1. Proposes collaboration patterns from seed definitions (`collaboration/seeds.py`)
2. Processes pattern approvals via `ApprovalGateway`

---

## File Map

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry point, `/analyze` endpoint, `create_agent_app()` with `evolution_excluded=True` |
| `service/agent.py` | `EvolutionAgent` class -- event handling, analysis orchestration |
| `service/global_analyzer.py` | `GlobalAnalyzer` -- cross-agent trace analysis engine |
