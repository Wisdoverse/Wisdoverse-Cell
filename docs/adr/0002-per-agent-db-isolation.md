# ADR-0002: Per-Agent Database and Redis Isolation

## Status
Accepted (2026-03-07)

## Context
All agents shared:
- Same PostgreSQL superuser (`projectcell`) with full access to all tables
- Same Redis database (db 0) with potential key collisions

This violates the principle of least privilege and makes it impossible to audit which agent accessed which data.

## Decision

### PostgreSQL
- Create per-agent database roles: `chat_agent`, `pjm_agent`, `sync_agent`,
  `analysis_agent`, `qa_agent`, `dev_agent`, and `evolution_agent`
- Grant table-level permissions (SELECT/INSERT/UPDATE/DELETE) only on each agent's own tables
- Analysis agent gets cross-agent SELECT for analytical queries
- Superuser retained for ai-core (manages shared models) and pg-backup

### Redis
- Assign per-agent database numbers: chat=1, pm=2, sync=3, analysis=4,
  qa=5, dev=6, and evolution=7
- EventBus always uses db 0 via `settings.redis_event_bus_url`
- Each agent reads REDIS_DB from environment variable

## Consequences

### Positive
- Least-privilege access — compromised agent can't access other agents' data
- Independent monitoring — per-db metrics in Redis
- No key collisions — agents can use same key names safely
- Audit trail — PostgreSQL logs show which role accessed what

### Negative
- More complex initialization (02-agent-users.sql)
- Credential management per agent (mitigated by env vars with defaults)
- Cross-agent queries require explicit GRANT

### Neutral
- No code changes needed beyond config — agents already use settings.redis_url
