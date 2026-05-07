# Self-Evolution System (`shared/evolution`)

> Agents that learn from their own execution traces.

## Overview

The self-evolution system enables Wisdoverse Cell agents to autonomously improve their skills (prompts, parameters, few-shot examples) based on execution data, human feedback, and cross-agent collaboration patterns. All changes are gated by safety mechanisms -- agents cannot modify their own code, only their skill configurations.

### Three Layers

| Layer | Scope | Description |
|-------|-------|-------------|
| **L1: Skill/Prompt** | Single agent | Optimize prompts, parameters, few-shot examples based on execution traces |
| **L2: Architecture** | Cross-agent | Global analysis by `evolution-module` to propose structural improvements |
| **L3: Collaboration** | Multi-agent | Discover and deploy multi-agent coordination patterns |

---

## Component Map

### Core (`shared/evolution/`)

| File | Description |
|------|-------------|
| `models.py` | Data models: `ExecutionTrace`, `SkillConfig`, `LLMCallRecord`, `Reflection`, `Experiment`, `MemoryEntry` |
| `trace_collector.py` | Captures execution traces around `handle_event` calls (timing, inputs, outputs, LLM calls) |
| `evaluator.py` | Scores execution traces using rule-based and semantic (LLM) evaluation |
| `skill_optimizer.py` | Generates improved `SkillConfig` versions based on reflections and traces |
| `self_reflector.py` | Analyzes batches of traces to identify success/failure patterns and optimization suggestions |
| `evolution_guard.py` | Circuit breaker for evolution: enforces rollback thresholds, max rollbacks per day |
| `kill_switch.py` | Redis-backed global kill switch to disable evolution system-wide in emergencies |
| `prompt_safety_scanner.py` | Validates that proposed prompt changes do not contain injection attacks or unsafe content |
| `evolved_agent.py` | `EvolvedAgent` wrapper -- adds execution tracing to any `BaseAgent` via composition |
| `agent_memory.py` | Per-agent key-value memory store (short-term and long-term) |
| `canary_router.py` | Routes a percentage of traffic to candidate skill versions for A/B testing |
| `config.py` | `EvolutionSettings` -- all configuration via `EVOLUTION_*` environment variables |

### Collaboration (`shared/evolution/collaboration/`)

| File | Description |
|------|-------------|
| `orchestrator.py` | Executes multi-agent collaboration patterns step by step |
| `shadow_runner.py` | Runs candidate patterns in shadow mode alongside production |
| `approval_gateway.py` | Human approval workflow for promoting patterns from shadow to active |
| `pattern_store.py` | CRUD storage for `CollaborationPattern` instances |
| `models.py` | `CollaborationPattern`, `CollaborationStep`, `ShadowRunResult`, `PatternStatus` |
| `condition_evaluator.py` | Evaluates trigger conditions to determine when a pattern should activate |
| `shadow_event_bus.py` | Isolated event bus for shadow execution (no side effects on production) |
| `seeds.py` | Pre-defined seed patterns for bootstrapping collaboration |

### Seeds (`shared/evolution/seeds/`)

| File | Description |
|------|-------------|
| `analysis_module.py` | Seed skill configurations for analysis-module |
| `chat_agent.py` | Seed skill configurations for chat-agent |
| `pjm_agent.py` | Seed skill configurations for pjm-agent |
| `requirement_manager.py` | Seed skill configurations for requirement-manager |
| `sync_module.py` | Seed skill configurations for sync-module |

### Database (`shared/evolution/db/`)

| File | Description |
|------|-------------|
| `tables.py` | SQLAlchemy table definitions for evolution data |
| `repository.py` | `EvolutionRepository` -- data access layer (Repository pattern) |
| `database.py` | `EvolutionDatabaseManager` -- async session management |

---

## How It Works

```
Agent receives Event
        |
        v
  EvolvedAgent.handle_event()
        |
        v
  TraceCollector.start() -----> delegates to inner agent
        |                              |
        v                              v
  TraceHandle records                results / error
  timing, inputs, outputs
        |
        v  [background, fire-and-forget]
  _post_execution()
        |
        +---> Persist trace to DB (EvolutionRepository)
        |
        +---> Evaluator.score_trace()  [if auto_optimize]
        |
        +---> CanaryRouter.record_result()  [if canary_enabled]
        |
        +---> SkillOptimizer.maybe_optimize()  [if auto_optimize]
                    |
                    v
              SelfReflector analyzes trace batch
                    |
                    v
              SkillOptimizer proposes new SkillConfig
                    |
                    v
              PromptSafetyScanner validates
                    |
                    v
              EvolutionGuard checks rollback limits
                    |
                    v
              CanaryRouter deploys as candidate (A/B test)
                    |
                    v
              SkillOptimizer.check_experiment()
              promotes or rolls back after enough samples
```

The `evolution-module` (L2) runs on a separate schedule, analyzing traces across all agents to propose architectural improvements. See `shared/capabilities/evolution/README.md`.

---

## Configuration

All settings use the `EVOLUTION_` prefix and can be overridden via environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `EVOLUTION_ENABLED` | `true` | Master switch for the evolution system |
| `EVOLUTION_TRACE_SAMPLING_RATE` | `1.0` | Fraction of events to trace (0.0-1.0) |
| `EVOLUTION_SELF_REFLECT_INTERVAL` | `50` | Trigger self-reflection every N executions |
| `EVOLUTION_ROLLBACK_THRESHOLD` | `0.10` | Success rate drop that triggers rollback |
| `EVOLUTION_MIN_SAMPLES` | `10` | Minimum traces before making decisions |
| `EVOLUTION_MAX_ROLLBACKS_PER_DAY` | `3` | Circuit breaker: max rollbacks in 24h |
| `EVOLUTION_MAX_PROMPT_LENGTH` | `50000` | Maximum allowed prompt length |
| `EVOLUTION_AUTO_OPTIMIZE` | `false` | Enable automatic optimization (Phase 2) |
| `EVOLUTION_CANARY_ENABLED` | `false` | Enable canary/A/B routing (Phase 2) |
| `EVOLUTION_EVALUATOR_SEMANTIC_ENABLED` | `false` | Enable LLM-based trace scoring (Phase 2) |
| `EVOLUTION_COLLABORATION_ENABLED` | `false` | Enable collaboration patterns (Phase 3) |
| `EVOLUTION_SHADOW_MAX_CONCURRENT` | `3` | Max concurrent shadow pattern runs |
| `EVOLUTION_SHADOW_MIN_RUNS_FOR_APPROVAL` | `20` | Min shadow runs before human review |
| `EVOLUTION_ADMIN_CHAT_ID` | `""` | Chat ID for admin notifications |
| `EVOLUTION_ADMIN_USER_IDS` | `[]` | User IDs authorized for pattern approval |

---

## Safety Mechanisms

### Kill Switch (`kill_switch.py`)

Redis-backed global toggle. When disabled, `EvolvedAgent` passes events directly to the inner agent with zero overhead. Operated via Redis key -- no restart required.

### PromptSafetyScanner (`prompt_safety_scanner.py`)

Validates all proposed prompt changes before deployment. Rejects prompts that:
- Contain injection patterns
- Exceed maximum length
- Include unsafe content or attempt to override system boundaries

### EvolutionGuard (`evolution_guard.py`)

Circuit breaker that prevents runaway optimization:
- Tracks success rate deltas per skill
- Triggers automatic rollback if success rate drops below `rollback_threshold`
- Enforces `max_rollbacks_per_day` limit -- if exceeded, evolution pauses until manual intervention

### Canary Routing (`canary_router.py`)

New skill versions are never deployed to 100% of traffic. The canary router:
- Caps traffic to candidate versions at 30% (`Experiment.traffic_pct`)
- Records candidate and control scores for each active experiment
- Keeps routing deterministic by trace ID, so retries use the same skill version

`SkillOptimizer.check_experiment()` concludes the experiment after both arms
reach `Experiment.min_samples`. A candidate is promoted only when it meets
`Experiment.min_improvement`; it is rolled back when degradation exceeds the
rollback threshold.

### Human-in-the-Loop

Collaboration patterns (L3) require explicit human approval before promotion from shadow to active status. The `ApprovalGateway` enforces this gate.
