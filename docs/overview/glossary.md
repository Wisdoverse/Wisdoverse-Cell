# Wisdoverse Cell Glossary

This glossary defines the core terms used across Wisdoverse Cell. Repository-facing definitions are English-first; non-English terms should appear only when they are stable external names, locale values, quoted source text, or fixtures.

---

## Architecture

**Agent** — An independently deployed business unit that inherits `BaseAgent`. Each agent owns its PostgreSQL user and Redis DB. Agents communicate through EventBus or HTTP REST.

**BaseAgent** — The base class for all agents. It defines `handle_event()`, `startup()`, and `shutdown()`.

**AgentClient** — HTTP REST client for synchronous cross-agent requests. Calls use `X-Internal-Key` for service authentication.

**Event** — Immutable message with an `event_type` in `{domain}.{action}` format, such as `requirement.created`. Events include `event_id`, `source_agent`, `payload`, `trace_id`, and schema version.

**EventBus** — Redis Streams based event bus for asynchronous agent communication. Producers use `XADD`; consumers use `XREADGROUP`.

**Circuit Breaker** — Failure-isolation pattern that opens after downstream failures pass a threshold. Used in LLMGateway to protect provider calls.

**LLMGateway** — Unified model access gateway with circuit breaking, budget control, tiered model selection, and optional LiteLLM routing for multiple providers.

**Gateway** — Go HTTP gateway that handles external webhook routing and signature verification for Feishu, WeCom, and related platforms.

**Shared** — The `shared/` package containing schemas, configuration, infrastructure, integrations, runtime helpers, and cross-agent utilities.

**Repository Pattern** — Data-access abstraction that keeps persistence details out of business logic.

---

## Project Management

**WBS** — Work Breakdown Structure. A hierarchical breakdown of project scope into manageable work packages.

**Decomposition** — LLM-assisted process that turns high-level requirements into user stories and tasks.

**User Story** — Requirement statement that captures role, desired capability, and value.

**Sprint** — Short iteration, usually one or two weeks, for delivering committed work.

**Milestone** — Project checkpoint that marks a meaningful delivery target.

**Bitable** — Feishu multidimensional table used for project data storage and operational views.

**OpenProject (OP)** — Open-source project management platform for task tracking, Gantt charts, and execution management.

**Backlog** — Collection of stories and tasks not yet planned into a sprint.

**Epic** — Larger requirement grouping that spans multiple user stories and often multiple sprints.

---

## Platform Integrations

**Feishu / Lark** — Collaboration platform used through bot, card, Bitable, and event APIs.

**Card** — Structured Feishu message with rich text and interactive buttons.

**Card Callback** — Gateway callback triggered when a user interacts with a Feishu card.

**Bot** — Automated endpoint for receiving and sending user messages.

**open_id** — Feishu user identifier. It is PII and must be protected.

**App Token** — Feishu application credential pair used to obtain tenant access tokens. It must never be logged.

**WeCom** — WeChat Work enterprise collaboration platform. Gateway supports both Feishu and WeCom channels.

**Tenant Access Token** — Feishu tenant-scoped access token with expiration and refresh requirements.

---

## Data and Security

**PII** — Personally Identifiable Information such as names, phone numbers, and email addresses.

**DSAR** — Data Subject Access Request. GDPR-style user rights flow for access, export, and deletion.

**X-Internal-Key** — Service-to-service authentication header required for internal AgentClient calls.

**Per-Agent Isolation** — Separate PostgreSQL users and Redis DBs per agent to limit blast radius.

**Prompt Injection** — Attack where a user attempts to manipulate model behavior through crafted input. Inputs must be sanitized and isolated before LLM calls.

**Human-in-the-Loop (HITL)** — Human approval step required for finance, legal, customer, and technical architecture decisions.

---

## Infrastructure

**Traefik** — L7 reverse proxy and load balancer for routing and TLS termination.

**PgBouncer** — PostgreSQL connection pooler that reduces connection overhead.

**Redis Streams** — Durable Redis stream data structure used by EventBus.

**Consumer Group** — Redis Streams consumption model that coordinates multiple consumers and ACK handling.

**NATS JetStream** — Optional durable messaging backend for higher-reliability event streaming.

**PostgreSQL** — Primary relational database accessed through async drivers.

**asyncpg** — Async PostgreSQL driver used by Python services.

---

## LLM

**Claude** — Anthropic large language model family that may be accessed through LiteLLM.

**Opus / Sonnet / Haiku** — Claude model tiers for complex reasoning, balanced work, and lightweight extraction/classification.

**Tool Calling** — LLM capability for invoking predefined functions or APIs during a conversation.

**RAG** — Retrieval-Augmented Generation. The system retrieves relevant context from Milvus and passes it to the LLM.

**Token** — Basic LLM text unit that drives usage and cost accounting.

**System Prompt** — Instruction block that defines an agent's role, boundaries, and output contract.

---

## Evolution System

**EvolvedAgent** — Wrapper that adds execution tracing to any `BaseAgent` without changing the business agent implementation.

**EvolutionGuard** — Circuit breaker for the evolution system. It tracks skill success rates and rolls back degraded versions.

**SelfReflector** — Batch analyzer for traces that identifies success patterns, failure patterns, and optimization suggestions.

**SkillConfig** — Versioned skill configuration containing system prompt, parameters, and few-shot examples.

**ExecutionTrace** — Full trace of one `handle_event` execution, including inputs, outputs, LLM calls, latency, status, and optional human score.

**CanaryRouter** — Router that sends a bounded portion of traffic to candidate skill versions for A/B testing.

**CollaborationPattern** — Multi-agent collaboration model with `proposed -> shadow -> active -> retired` lifecycle.

**ShadowRunner** — Side-effect-free runner for validating candidate collaboration patterns before activation.

**Kill Switch** — Redis-backed global switch that disables the evolution system without restarting services.

**RuntimePlugin** — `AgentRuntime` extension interface with `wrap_agent`, `startup`, `shutdown`, and `health_check` hooks.

**AgentRuntime** — Lifecycle manager for plugins, startup/shutdown ordering, event loops, and health aggregation.

---

## Development

**ADR** — Architecture Decision Record.

**Conventional Commits** — Commit format such as `feat(scope): description`.

**Pydantic v2** — Data validation library used for schemas and settings.

**ULID** — Time-sortable unique identifier used for event and entity IDs.

**trace_id** — Distributed tracing identifier propagated through events and logs.

**FastAPI** — Async Python web framework used by agent HTTP APIs.

**Acceptance Framework** — `.acceptance/` quality gate framework with L0 static checks, L1 behavioral checks, and L2 architecture checks.

**QA Agent** — Agent that runs automated acceptance checks and reports results to EventBus, Feishu, and GitLab MR comments.

**Evolution Agent** — Agent that analyzes traces and generates L1/L2/L3 optimization recommendations.

**Milvus** — Vector database used for semantic search and similarity matching.

**VectorStore** — `shared/infra/vector_store.py` abstraction for embedding storage, search, and retrieval.

---

## Abbreviations

| Abbreviation | Meaning |
|--------------|---------|
| US | User Story |
| WBS | Work Breakdown Structure |
| OP | OpenProject |
| PII | Personally Identifiable Information |
| DSAR | Data Subject Access Request |
| RAG | Retrieval-Augmented Generation |
| ADR | Architecture Decision Record |
| HITL | Human-in-the-Loop |
| ULID | Universally Unique Lexicographically Sortable Identifier |
| L1/L2/L3 | Evolution layers for skill, architecture, and collaboration |
