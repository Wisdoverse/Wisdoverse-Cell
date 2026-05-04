# Wisdoverse Cell Incident Response Playbook

> **Version**: v2026.03 | **Standard**: Google SRE Incident Management | **Maintainer**: Platform Team

---

## Table of Contents

1. [Severity Classification](#1-severity-classification)
2. [Response Protocol](#2-response-protocol)
3. [Playbooks](#3-playbooks)
4. [Communication Templates](#4-communication-templates)
5. [Recovery Procedures](#5-recovery-procedures)

---

## 1. Severity Classification

| Severity | Name | Definition | Examples | Response Time |
|:--------:|------|-----------|----------|:-------------:|
| **SEV-1** | System Down | All agents unreachable; core business flow completely broken | EventBus down, PostgreSQL crash, Traefik unreachable | **5 min** |
| **SEV-2** | Degraded | Some agents or major features unavailable; partial service loss | LLM API circuit breaker open, PJM Agent OOM, Sync Agent crash loop | **15 min** |
| **SEV-3** | Minor Issue | Non-critical feature broken; workaround available | Daily report generation failed, one Feishu webhook retrying, single agent memory spike | **1 hour** |
| **SEV-4** | Cosmetic / Doc | UI glitch, documentation error, non-functional issue | Typo in card message, stale dashboard panel, outdated API docs | **Next business day** |

### Severity Escalation Rules

- If a SEV-3 is unresolved after **2 hours**, escalate to SEV-2.
- If a SEV-2 is unresolved after **1 hour**, escalate to SEV-1.
- Any incident involving **data loss** or **security breach** is automatically SEV-1.

---

## 2. Response Protocol

### 2.1 Notification Matrix

| Severity | Who to Notify | How |
|:--------:|---------------|-----|
| **SEV-1** | CTO + Platform Team + All Agent Owners | Feishu urgent group + phone call |
| **SEV-2** | Platform Team + Affected Agent Owner | Feishu incident group |
| **SEV-3** | Agent Owner | Feishu incident group |
| **SEV-4** | Filed as issue | GitLab issue tracker |

### 2.2 Incident Roles

| Role | Responsibility |
|------|---------------|
| **Incident Commander (IC)** | Coordinates response, makes escalation decisions, communicates status |
| **Primary Responder** | Investigates root cause, applies fix |
| **Communications Lead** | Posts status updates to Feishu group using templates (Section 4) |

For SEV-3/SEV-4, one person fills all roles. For SEV-1/SEV-2, assign separate people.

### 2.3 Escalation Timeline

```
T+0 min    Incident detected (alert fires or manual report)
T+5 min    IC assigned, severity classified
T+10 min   First status update posted to Feishu group
T+30 min   Root cause identified OR escalation if not
T+60 min   Fix applied OR escalation to next severity
T+2 hours  SEV-2 unresolved → escalate to SEV-1
T+4 hours  Post-incident review scheduled (SEV-1/SEV-2)
T+24 hours Post-incident review document completed
```

---

## 3. Playbooks

Each playbook follows: **Symptoms → Diagnosis → Fix → Prevention**.

---

### 3.1 PostgreSQL Connection Exhaustion

**Severity**: SEV-2

**Symptoms**:
- Agents return HTTP 500 with "connection pool exhausted" or "too many connections"
- Prometheus alert: `PostgresConnectionUsageHigh` (> 80%)
- Health endpoints return degraded status

**Diagnosis**:

```bash
# Check current connections by user and state
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT usename, state, count(*)
    FROM pg_stat_activity
    GROUP BY usename, state
    ORDER BY count DESC;
  "

# Check connection usage percentage
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT count(*) AS current,
           setting::int AS max,
           round(count(*)::numeric / setting::numeric * 100, 1) AS pct
    FROM pg_stat_activity, pg_settings
    WHERE pg_settings.name = 'max_connections'
    GROUP BY setting;
  "

# Check PgBouncer pool status
docker compose -f docker/compose/docker-compose.base.yml exec pgbouncer \
  psql -p 6432 -U projectcell pgbouncer -c "SHOW POOLS;"
```

**Fix**:

```bash
# Step 1: Kill idle connections older than 10 minutes (non-superuser only)
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE state = 'idle'
      AND query_start < now() - interval '10 minutes'
      AND usename != 'projectcell';
  "

# Step 2: If PgBouncer pool is saturated, restart PgBouncer
docker compose -f docker/compose/docker-compose.base.yml restart pgbouncer

# Step 3: If still exhausted, restart the offending agent
docker compose -f docker/compose/docker-compose.app.yml restart <agent-name>
```

**Prevention**:
- Ensure all agents use PgBouncer (port 6432) instead of direct PostgreSQL (port 5432)
- Set `db_pool_size` in agent config to a reasonable value (default: 5 per agent)
- Monitor `PostgresConnectionUsageHigh` alert and scale before hitting limits

---

### 3.2 Redis / EventBus Backlog > 10k Messages

**Severity**: SEV-2

**Symptoms**:
- Events are delayed or not being processed
- Prometheus alert: `EventQueueBacklogHigh` (> 5000 pending messages)
- Agent logs show increasing consumer lag

**Diagnosis**:

```bash
# Check EventBus queue length
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n 0 XLEN "event_stream"

# Check consumer group lag
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n 0 XINFO GROUPS "event_stream"

# Check Redis memory
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human"

# Check which agents are consuming slowly
curl -s 'http://localhost:9090/api/v1/query?query=event_queue_length' | jq '.data.result'
```

**Fix**:

```bash
# Step 1: Identify and restart slow/stuck consumer agents
docker compose -f docker/compose/docker-compose.app.yml logs --tail=100 <agent-name> | grep -i "error\|timeout\|stuck"
docker compose -f docker/compose/docker-compose.app.yml restart <agent-name>

# Step 2: If agent is crash-looping, check for OOM or dependency failure
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Step 3: If backlog is from a non-critical event type, trim the stream (CAUTION: data loss)
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n 0 XTRIM "event_stream" MAXLEN ~ 1000

# Step 4: If Redis memory is near limit, clear non-essential keys
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n 0 DBSIZE
```

**Prevention**:
- Monitor `EventQueueBacklogHigh` alert with a low threshold (1000 warning, 5000 critical)
- Ensure each consumer group ACKs events promptly
- Set Redis `maxmemory-policy` to `allkeys-lru` for non-EventBus databases

---

### 3.3 LLM API Rate Limiting / Circuit Breaker Open

**Severity**: SEV-2

**Symptoms**:
- Agent responses fall back to degraded/static content
- Logs show `CircuitBreakerError` or `429 Too Many Requests`
- Prometheus alert: `LLMErrorRateHigh` (> 10%)
- Prometheus alert: `LLMDailyBudgetExceeded`

**Diagnosis**:

```bash
# Check LLM error rate
curl -s 'http://localhost:9090/api/v1/query?query=job:llm_error_rate:ratio_5m' | jq '.data.result'

# Check daily budget consumption
curl -s 'http://localhost:9090/api/v1/query?query=llm_daily_cost_dollars' | jq '.data.result[0].value[1]'

# Check circuit breaker state in agent logs
docker compose -f docker/compose/docker-compose.app.yml logs --tail=100 ai-core | grep -i "circuit\|rate.limit\|429"

# Check LiteLLM proxy and provider status
# Visit the active provider status page if the proxy is healthy.
```

**Fix**:

```bash
# Step 1: If rate-limited, reduce concurrency by scaling down
make scale-ai-core N=1

# Step 2: If budget exceeded, the LLMGateway auto-downgrades models
# Verify by checking which model is in use:
docker compose -f docker/compose/docker-compose.app.yml logs --tail=50 ai-core | grep -i "model"

# Step 3: If circuit breaker is stuck open, restart the agent to reset
docker compose -f docker/compose/docker-compose.app.yml restart ai-core

# Step 4: If the provider is down, wait for recovery. Agents should use fallback logic.
# Verify fallback is working:
curl -f http://localhost:8000/health/ready
```

**Prevention**:
- Use tiered models: Opus for complex tasks, Sonnet for chat, Haiku for summaries
- Set conservative daily budget in `LLMGateway` configuration
- Every LLM call site must implement `try/except CircuitBreakerError` with a fallback
- Monitor `LLMDailyBudgetExceeded` alert

---

### 3.4 Agent OOM (Out of Memory)

**Severity**: SEV-2

**Symptoms**:
- Agent container repeatedly killed and restarted
- `docker stats` shows container at 100% memory limit
- Prometheus alert: `ContainerOOMKilled`

**Diagnosis**:

```bash
# Check which container is OOM-killed
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" | sort -k3 -rn

# Check container restart count
docker inspect --format='{{.RestartCount}} {{.Name}}' $(docker ps -aq) | sort -rn | head -10

# Check agent-specific memory usage patterns
docker compose -f docker/compose/docker-compose.app.yml logs --tail=200 <agent-name> | grep -i "memory\|oom\|killed"

# Check for memory leaks — look for growing object counts
docker compose -f docker/compose/docker-compose.app.yml exec <agent-name> \
  python -c "import gc; gc.collect(); print(len(gc.get_objects()))"
```

**Fix**:

```bash
# Step 1: Restart the agent immediately to restore service
docker compose -f docker/compose/docker-compose.app.yml restart <agent-name>

# Step 2: Temporarily increase memory limit in docker-compose
# Edit the deploy.resources.limits.memory for the agent, then:
docker compose -f docker/compose/docker-compose.app.yml up -d <agent-name>

# Step 3: If caused by large LLM responses, check payload sizes in logs
docker compose -f docker/compose/docker-compose.app.yml logs --tail=500 <agent-name> | grep -i "payload_size\|content_length"
```

**Prevention**:
- Set appropriate `deploy.resources.limits.memory` for each agent (default: 512M)
- Use streaming for large LLM responses where possible
- Avoid accumulating large lists in memory; use generators or pagination
- Monitor `ContainerOOMKilled` alert

---

### 3.5 Milvus Vector Search Timeout

**Severity**: SEV-3

**Symptoms**:
- Evolution Agent or agents using vector search return slow or empty results
- Logs show `MilvusTimeout` or `ConnectionError` from `shared.infra.milvus_store`
- Milvus health endpoint unresponsive

**Diagnosis**:

```bash
# Check Milvus container health
docker compose -f docker/compose/docker-compose.base.yml exec milvus \
  curl -s http://localhost:9091/healthz

# Check container resource usage
docker stats --no-stream milvus

# Check connection from agent side
docker compose -f docker/compose/docker-compose.app.yml exec <agent-name> \
  python -c "
from shared.infra.milvus_store import MilvusVectorStore
import asyncio
async def check():
    store = MilvusVectorStore()
    await store.initialize()
    print('Connected OK')
    await store.close()
asyncio.run(check())
"

# Check collection sizes
docker compose -f docker/compose/docker-compose.base.yml logs --tail=50 milvus
```

**Fix**:

```bash
# Step 1: Restart the vector store container
docker compose -f docker/compose/docker-compose.base.yml restart milvus

# Step 2: If data is corrupted, rebuild the index
# (This depends on the specific vector store implementation)

# Step 3: If persistent, increase memory limit for the vector store
# Edit docker-compose.base.yml: milvus deploy.resources.limits.memory
docker compose -f docker/compose/docker-compose.base.yml up -d milvus
```

**Prevention**:
- Monitor Milvus health endpoint
- Set appropriate memory limits (default: 2G)
- Implement timeout and fallback in `shared.infra.milvus_store`
- Periodically compact collections to reduce index size

---

### 3.6 Evolution System Runaway (Too Many Rollbacks)

**Severity**: SEV-2

**Symptoms**:
- Agent behavior oscillates between old and new skill versions
- Logs show repeated `evolution.rollback` events
- EvolutionGuard rate limiting kicks in
- KillSwitch may activate, disabling evolution for an agent

**Diagnosis**:

```bash
# Check evolution rollback frequency
docker compose -f docker/compose/docker-compose.app.yml logs --tail=200 <agent-name> | grep -i "rollback\|evolution\|killswitch"

# Check if KillSwitch is active
docker compose -f docker/compose/docker-compose.app.yml logs --tail=50 <agent-name> | grep -i "killswitch"

# Check Evolution Agent analysis
docker compose -f docker/compose/docker-compose.app.yml logs --tail=100 evolution-agent | grep -i "runaway\|oscillat"

# Check SkillStore for conflicting versions
curl -f http://localhost:<evolution-agent-port>/api/v1/evolution/skills/<agent-id>
```

**Fix**:

```bash
# Step 1: Activate KillSwitch to freeze evolution for the affected agent
# This is typically done via the Evolution Agent API or direct config

# Step 2: Identify the oscillating skill and pin to a known-good version
# Check SkillStore for the last stable version

# Step 3: Clear the CanaryRouter state to stop A/B routing
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n 0 DEL "evolution:canary:<agent-id>"

# Step 4: Restart the affected agent with evolution disabled temporarily
# Set EVOLUTION_ENABLED=false in the agent's environment, then restart
docker compose -f docker/compose/docker-compose.app.yml up -d <agent-name>
```

**Prevention**:
- EvolutionGuard enforces rate limits on skill changes (configured in `shared/evolution/`)
- KillSwitch auto-activates after N consecutive rollbacks (default: 3)
- All L2/L3 changes require human approval via ApprovalGateway
- Monitor `evolution.rollback` event frequency

---

### 3.7 NATS JetStream Consumer Lag

**Severity**: SEV-3

**Symptoms**:
- Messages between agents are delayed by seconds or minutes
- NATS monitoring shows consumer lag growing
- Agents subscribed to JetStream subjects fall behind

**Diagnosis**:

```bash
# Check NATS cluster health
curl -s http://localhost:8222/varz | jq '{server_id, version, connections, jetstream}'

# Check JetStream stream info
curl -s http://localhost:8222/jsz | jq '.streams[] | {name, state: .state}'

# Check consumer lag for specific streams
curl -s http://localhost:8222/jsz?consumers=true | jq '.streams[].consumers[] | {name, num_pending, num_ack_pending}'

# Check NATS cluster connectivity
curl -s http://localhost:8222/routez | jq '.routes[] | {rid, ip, port}'
```

**Fix**:

```bash
# Step 1: Restart slow consumers
docker compose -f docker/compose/docker-compose.app.yml restart <agent-name>

# Step 2: If consumer is permanently stuck, delete and recreate the consumer
# (Use NATS CLI if available)
# nats consumer rm <stream> <consumer>

# Step 3: If NATS node is unhealthy, restart it
docker compose -f docker/compose/docker-compose.base.yml restart nats-1

# Step 4: If cluster quorum is lost (multiple nodes down), restart all NATS nodes
docker compose -f docker/compose/docker-compose.base.yml restart nats-1 nats-2 nats-3
```

**Prevention**:
- Monitor NATS consumer lag via Prometheus (nats-exporter on port 7777)
- Set appropriate `MaxDeliver` and `AckWait` for JetStream consumers
- Ensure NATS cluster has 3 nodes for quorum tolerance

---

### 3.8 Feishu Webhook Delivery Failure

**Severity**: SEV-3

**Symptoms**:
- Bot messages not appearing in Feishu groups
- Card callbacks not reaching the system
- Logs show HTTP 4xx/5xx from Feishu API
- Prometheus alert: `FeishuWebhookDeliveryFailure`

**Diagnosis**:

```bash
# Check outbound delivery logs
docker compose -f docker/compose/docker-compose.app.yml logs --tail=100 ai-core | grep -i "feishu\|delivery\|webhook"

# Check Go gateway webhook reception
docker compose -f docker/compose/docker-compose.app.yml logs --tail=100 gateway | grep -i "feishu\|webhook\|callback"

# Check if Feishu access token is valid
docker compose -f docker/compose/docker-compose.app.yml exec ai-core \
  python -c "
from shared.integrations.feishu import FeishuClient
import asyncio
async def check():
    client = FeishuClient()
    token = await client.get_tenant_access_token()
    print(f'Token valid: {bool(token)}')
asyncio.run(check())
"

# Check Feishu API status
# Visit: https://open.feishu.cn/document/server-docs/overview
```

**Fix**:

```bash
# Step 1: If token expired, the client should auto-refresh. Force refresh:
docker compose -f docker/compose/docker-compose.app.yml restart ai-core

# Step 2: If Feishu app credentials are wrong, check .env
# Verify: FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_VERIFICATION_TOKEN, FEISHU_ENCRYPT_KEY

# Step 3: If webhook URL changed, update Traefik route or Feishu app config
# Check Traefik routes:
curl -s http://localhost:8081/api/http/routers | jq '.[] | select(.rule | contains("webhook"))'

# Step 4: If Feishu API is rate-limiting, back off and retry
# Check rate limit headers in logs
docker compose -f docker/compose/docker-compose.app.yml logs --tail=50 ai-core | grep -i "rate.limit\|429\|retry"
```

**Prevention**:
- Monitor `FeishuWebhookDeliveryFailure` alert
- Implement retry with exponential backoff in `shared.integrations.feishu`
- Cache Feishu access tokens with proper TTL
- Set up a secondary notification channel (email/WeCom) for critical alerts

---

## 4. Communication Templates

### 4.1 Status Update Template (Feishu Group)

Use this template for posting to the incident Feishu group:

```
[Incident Update — SEV-{1/2/3}]

Status: {Investigating | Identified | Fixing | Resolved}
Impact: {Description of user-facing impact}
Affected: {List of affected agents/services}

Current actions:
- {What is being done right now}

Next update: {Time of next update, e.g., "in 15 minutes" or "when fix is deployed"}

IC: {Name}
```

**Example**:

```
[Incident Update — SEV-2]

Status: Identified
Impact: Chat Agent responding with fallback messages (no LLM-powered responses)
Affected: chat-agent, pjm-agent (PM query responses degraded)

Current actions:
- Root cause: Anthropic API rate limiting (429 responses)
- Scaled down ai-core replicas from 3 to 1 to reduce request rate
- Monitoring circuit breaker state for recovery

Next update: in 15 minutes

IC: Zhang Wei
```

### 4.2 Post-Incident Review Template

Create a document in `docs/incidents/YYYY-MM-DD-<short-title>.md`:

```markdown
# Post-Incident Review: {Title}

> **Date**: {YYYY-MM-DD}
> **Duration**: {Start time} — {End time} ({total duration})
> **Severity**: SEV-{1/2/3}
> **IC**: {Name}

## Summary

{1-2 sentence description of what happened and the user-facing impact.}

## Timeline (UTC)

| Time | Event |
|------|-------|
| HH:MM | {Alert fired / Issue reported} |
| HH:MM | {IC assigned, investigation started} |
| HH:MM | {Root cause identified} |
| HH:MM | {Fix applied} |
| HH:MM | {Service fully recovered} |

## Root Cause

{Technical explanation of what went wrong and why.}

## Impact

- **Users affected**: {Number or description}
- **Duration of impact**: {Minutes/hours}
- **Data loss**: {Yes/No — if yes, describe}

## What Went Well

- {Thing that worked}
- {Thing that worked}

## What Went Wrong

- {Thing that failed or was slow}
- {Thing that failed or was slow}

## Action Items

| Action | Owner | Priority | Due Date |
|--------|-------|:--------:|----------|
| {Preventive measure} | {Name} | P1 | {Date} |
| {Monitoring improvement} | {Name} | P2 | {Date} |
| {Documentation update} | {Name} | P3 | {Date} |
```

---

## 5. Recovery Procedures

### 5.1 Database Restore from Backup

**When to use**: Data corruption, accidental deletion, or catastrophic PostgreSQL failure.

```bash
# Step 1: Stop all application services to prevent writes
docker compose -f docker/compose/docker-compose.app.yml stop

# Step 2: List available backups
ls -la backups/*.dump

# Step 3: Option A — Restore to existing database (DESTRUCTIVE: overwrites current data)
docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  pg_restore -U projectcell -d projectcell --clean --if-exists --no-owner \
  < backups/projectcell_YYYYMMDD_HHMMSS.dump

# Step 3: Option B — Restore to a new database (SAFE: preserves current data)
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  createdb -U projectcell projectcell_restored

docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  pg_restore -U projectcell -d projectcell_restored --no-owner \
  < backups/projectcell_YYYYMMDD_HHMMSS.dump

# Step 4: Re-run per-agent permission grants
docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  sh /docker-entrypoint-initdb.d/02-agent-users.sh

docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  psql -U projectcell -d projectcell -f /docker-entrypoint-initdb.d/02-agent-users.sql

# Step 5: Restart application services
docker compose -f docker/compose/docker-compose.app.yml start

# Step 6: Verify agent health
curl -f http://localhost:8000/health/ready
curl -f http://localhost:8012/health/ready
```

### 5.2 Redis Flush and Rebuild

**When to use**: Redis data corruption, maxmemory reached with `noeviction` policy, or persistent OOM.

```bash
# Step 1: Assess impact — which Redis databases are affected
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli INFO keyspace

# Step 2: Option A — Flush a specific agent's database (non-destructive to EventBus)
# Agent databases are db 1-15; EventBus is always db 0
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n <agent-db-number> FLUSHDB

# Step 2: Option B — Flush ALL databases (CAUTION: destroys EventBus state too)
# Only use this as a last resort
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli FLUSHALL

# Step 3: Restart Redis to reclaim memory
docker compose -f docker/compose/docker-compose.base.yml restart redis-master

# Step 4: Wait for Redis to be healthy
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli ping
# Expected: PONG

# Step 5: Restart all agents to reconnect and rebuild caches
docker compose -f docker/compose/docker-compose.app.yml restart

# Step 6: Verify EventBus is functioning
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli -n 0 XINFO STREAM "event_stream"
```

**Note**: Flushing db 0 (EventBus) causes in-flight events to be lost. Schedule this during a maintenance window if possible.

### 5.3 Agent Force Restart Sequence

**When to use**: Multiple agents in a bad state, cascade failure, or after infrastructure recovery.

The restart order matters due to dependencies. Follow this sequence:

```bash
# Phase 1: Verify infrastructure is healthy
docker compose -f docker/compose/docker-compose.base.yml exec postgres pg_isready
docker compose -f docker/compose/docker-compose.base.yml exec redis-master redis-cli ping
curl -s http://localhost:8222/healthz

# Phase 2: Restart infrastructure if needed
docker compose -f docker/compose/docker-compose.base.yml restart postgres redis-master nats-1 nats-2 nats-3
# Wait for all to be healthy
sleep 10
make ps

# Phase 3: Restart gateway first (it handles all inbound traffic)
docker compose -f docker/compose/docker-compose.app.yml restart gateway
sleep 5

# Phase 4: Restart core agents (no inter-agent dependencies)
docker compose -f docker/compose/docker-compose.app.yml restart ai-core
sleep 5

# Phase 5: Restart dependent agents one by one
docker compose restart requirement-manager
sleep 3
docker compose restart sync-agent
sleep 3
docker compose restart pjm-agent
sleep 3
docker compose restart chat-agent
sleep 3
docker compose restart analysis-agent
sleep 3
docker compose restart evolution-agent

# Phase 6: Restart frontend
docker compose -f docker/compose/docker-compose.app.yml restart web

# Phase 7: Verify all agents are healthy
for port in 8000 8011 8012 8013 8014; do
  echo "Port $port: $(curl -sf http://localhost:$port/health | jq -r '.status')"
done

# Phase 8: Verify end-to-end by sending a test event
# See Section 2.5 of ONBOARDING.md for a test event script
```

### 5.4 Full Stack Cold Start

**When to use**: Complete environment rebuild after catastrophic failure or for a new deployment.

```bash
# Step 1: Bring everything down and clean
make down-dev
docker volume prune -f

# Step 2: Start infrastructure
make up-infra
# Wait for all containers to be healthy
sleep 30
make ps

# Step 3: Verify infrastructure
docker compose -f docker/compose/docker-compose.base.yml exec postgres pg_isready
docker compose -f docker/compose/docker-compose.base.yml exec redis-master redis-cli ping

# Step 4: If restoring from backup, do it now (see Section 5.1)

# Step 5: Start application stack
make up-dev

# Step 6: Run health checks
make ps
curl -f http://localhost/health
```

---

> **Document maintenance**: This playbook should be updated after every SEV-1 or SEV-2 post-incident review. If a new failure mode is discovered, add a playbook entry to Section 3.
