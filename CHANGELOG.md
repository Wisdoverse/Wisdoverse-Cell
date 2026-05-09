# Changelog

All notable changes to Wisdoverse Cell are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
for tagged releases. Pre-1.0 minor versions may include breaking changes; the
release notes call out breaking changes explicitly under a `Breaking` heading
when they apply.

## [Unreleased]

### Added

- (no entries yet)

### Changed

- (no entries yet)

### Fixed

- (no entries yet)

### Security

- (no entries yet)

## [0.3.0] - 2026-04-02

### Added
- LLM Error Taxonomy: 6 error categories with per-category retry strategies (`shared/infra/llm_errors.py`)
- ConversationEngine: shared multi-turn tool-calling loop with AsyncGenerator streaming (`shared/infra/conversation_engine.py`)
- MicroCompact: free pre-pass clearing stale tool_result content by block count
- ReactiveCompact: emergency compression on prompt-too-long (ContentSizeError)
- Prometheus counters: `projectcell_llm_error_total`, `projectcell_llm_fallback_total`
- 133 new tests across all P0 units (error taxonomy, retry, compression, engine, integration)

### Changed
- LLM Gateway: tenacity replaced by custom `_call_with_recovery()` loop enabling model fallback and ReactiveCompact mid-retry
- Context Compressor: 3-layer pipeline (MicroCompact → L1 trim → L2 summarize)
- chat_agent: migrated from ad-hoc 90-line tool loop to ConversationEngine
- chat_agent system prompt: restructured following Claude Code pattern (Identity → System → Tasks → Style), aligned with Coordinator architecture (chat_agent = front desk, not CEO)

### Fixed
- ContentSizeError detection: correctly matches HTTP 400 BadRequestError via message pattern (not HTTP 413)
- Circuit breaker records exactly 1 failure after all retries+fallback exhausted (not per-attempt)

## [0.2.0] - 2026-03-07

### Added
- feat/pm-system: Complete PM system with 4 agents (Chat, PM, Sync, Analysis)
- Agent decoupling: HTTP REST inter-agent communication via `AgentClient` / `PMAgentClient`
- PJM Agent REST API (`/api/v1/pm/decompose/{wp_id}/approve|reject|retry`)
- EventBus migrated from Redis LIST to Redis Streams (XADD/XREADGROUP)
- LLM Gateway with circuit breaker, retry, and Redis-based daily budget metering
- 51 Prometheus alert rules + AlertManager Feishu webhook integration
- DSAR API for GDPR/PIPL data subject access requests
- Per-agent Redis db isolation and PostgreSQL user isolation
- Internal service authentication (`X-Internal-Key` header)
- Unified ErrorResponse format across all agents
- `@register_tool` decorator pattern for ToolExecutor
- Daily task dispatch (9:00) and progress collection (17:30)
- Decomposition approval cards with reject reason input
- Card operation audit logging (queryable via Claude)
- ADR-0001 through ADR-0004 architecture decision records

### Changed
- Runtime versions: Python 3.13, Rust 1.86, PostgreSQL 18, Redis 8
- **Agent decoupling**: `requirement_manager` no longer imports `pjm_agent` directly; uses HTTP REST via `PMAgentClient`
- **channel_gateway**: moved from `agents/` to `shared/services/channel_gateway/` (infrastructure, not a business agent)
- Chat Agent: all LLM calls via centralized LLMGateway (no direct provider SDK clients)
- Tiered model strategy: Sonnet (chat), Opus (decompose), Haiku (summary) — 58% cost reduction
- PMAgent God Class split into DecompositionOrchestrator
- APScheduler: all agents use `workers=1`, jobs with `replace_existing=True`
- Rolling updates: `deploy.update_config` with start-first strategy
- Dockerfile: removed `pjm_agent` COPY from `requirement_manager` and `ai-core` targets

### Fixed
- SEC-005: Webhook signature timing attack fixed with constant-time comparison
- SEC-003: Prompt injection defense (XML escaping, no PII in LLM prompt)
- COMP-C03: `ANTHROPIC_BASE_URL` proxy enforcement (raise on violation)
- DR-001: EventBus queue overflow (maxlen + TTL)
- PERF-C02: `daily_tasks` N+1 query eliminated
- FE-C07: Card callback 12s timeout (vs Feishu 15s limit)

### Security
- Internal API authentication via `INTERNAL_SERVICE_KEY`
- Per-agent database user isolation with table-level GRANT
- Webhook signature constant-time comparison
- Prompt injection prevention (XML delimiter isolation)
- PII removed from LLM system prompts
- Data residency: enforce `ANTHROPIC_BASE_URL` proxy

## [0.1.0] - 2026-01-25
### Added
- Initial release: Requirement Manager Agent (M1-M4)
- Initial API gateway with gRPC forwarding; current gateway runtime is Rust.
- EventBus (Redis LIST), LLM Gateway, BaseAgent
- Feishu deep integration (Bot, Cards, Events)
- Next.js Frontend (Dashboard, Requirements, i18n)

[Unreleased]: https://github.com/Wisdoverse/Wisdoverse-Cell/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Wisdoverse/Wisdoverse-Cell/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Wisdoverse/Wisdoverse-Cell/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Wisdoverse/Wisdoverse-Cell/releases/tag/v0.1.0
