# ADR-0003: Tiered LLM Model Strategy

## Status
Accepted (2026-03-07)

## Context
All LLM calls used Claude Opus ($15/$75 per million tokens), resulting in estimated monthly costs of $2,400 for a 10-person team. Most use cases (chat, summaries) don't require Opus-level reasoning.

## Decision
Implement three-tier model strategy:
- **Sonnet** ($3/$15): Chat conversations, tool calling, daily interactions
- **Opus** ($15/$75): WBS decomposition (requires deep reasoning)
- **Haiku** ($1/$5): Summaries, report generation, budget-exceeded fallback

Budget enforcement via Redis:
- Daily cost tracked with INCRBYFLOAT
- When exceeded, auto-downgrade to Haiku
- Configurable via LLM_DAILY_BUDGET_USD

## Consequences

### Positive
- Estimated cost reduction: $2,400 → $1,010/month (-58%)
- Automatic degradation prevents runaway costs
- Redis-based tracking accurate across workers

### Negative
- Sonnet may occasionally produce lower-quality tool calling
- Budget downgrade affects all agents equally

### Neutral
- No user-visible quality difference for chat (Sonnet is sufficient)
- Opus reserved for high-value decomposition tasks
