# ADR 0004: Inter-Agent HTTP Communication

## Status
Accepted

## Date
2026-03-07

## Context
requirement_manager was directly importing and calling pjm_agent's Python objects
in-process (`from agents.capabilities.project_management.service.agent import agent`). This created
deployment coupling: both agents had to run in the same process, pjm_agent code
had to be COPY'd into requirement_manager's Docker image, and independent scaling
was impossible.

The Go gateway already followed the correct pattern: HTTP calls to pjm_agent's
address (`pjm_agent_addr`).

## Decision
All inter-agent **synchronous** calls use HTTP REST APIs. Each agent exposes its
own FastAPI endpoints. Callers use typed HTTP clients (e.g., `PMAgentClient`)
from `shared/services/agent_client.py`.

**Asynchronous** communication continues to use Redis Streams EventBus.

### Communication Matrix

| From | To | Method | Use Case |
|------|-----|--------|----------|
| sync_agent | pjm_agent | EventBus | Task needs decomposition |
| pjm_agent | sync_agent | EventBus | Decomposition completed |
| CardHandler | pjm_agent | HTTP | Approve/reject decomposition |
| Go gateway | pjm_agent | HTTP | Approve/reject decomposition |
| chat_agent | pjm_agent | EventBus | PM status query |
| pjm_agent | chat_agent | EventBus | PM query response |

### Configuration

Each agent's URL is configured via environment variable:
- `PM_AGENT_URL` (default: `http://pjm-agent:8012`)

### Security

All inter-agent HTTP calls include `X-Internal-Key` header for authentication,
verified by the receiving agent's middleware.

## Consequences

### Positive
- Each agent is independently deployable and scalable
- No cross-agent Python imports (clean dependency graph)
- Consistent with Go gateway's existing HTTP pattern
- Service discovery via Docker Compose DNS (or K8s service names)
- Typed clients provide compile-time-like safety

### Negative
- Adds network latency (~1-5ms within Docker network)
- Requires PM_AGENT_URL configuration per environment
- HTTP errors need proper handling (timeouts, retries)
- Additional infrastructure dependency (network between containers)

### Neutral
- EventBus pattern unchanged (already decoupled)
- Shared library imports (`shared/`) remain (standard SDK pattern)
