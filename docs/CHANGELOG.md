# Changelog

All notable changes to Wisdoverse Cell are documented here.

This changelog is English-first and follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- QA Agent automated code-quality acceptance through the Acceptance Framework and AI Team Workflow.
- Complete self-evolution system: L1 skill/prompt optimization, L2 architecture optimization, and L3 agent-team collaboration optimization.
- Reflection Chain and skill-adherence evaluation.

## [2026-04-02] - P0 Architecture: ConversationEngine + Error Taxonomy

### Added
- LLM Error Taxonomy with 6 error categories and category-specific retry strategies in `shared/infra/llm_errors.py`.
- ConversationEngine, a shared multi-turn tool-calling engine with AsyncGenerator event streaming in `shared/infra/conversation_engine.py`.
- MicroCompact for free pre-cleanup of stale `tool_result` blocks.
- ReactiveCompact for prompt-too-long emergency compression recovery.
- Prometheus metrics: `wisdoverse-cell_llm_error_total` and `wisdoverse-cell_llm_fallback_total`.
- 133 new tests covering the P0 unit surface.

### Changed
- Replaced tenacity in LLM Gateway with custom `_call_with_recovery()` to support model fallback and compression recovery.
- Updated Context Compressor to a three-layer pipeline: MicroCompact -> L1 -> L2.
- Migrated `chat_agent` to ConversationEngine and rewrote the system prompt around the Claude Code operating pattern.

## [2026-03-18] - Agent Runtime and Infrastructure Upgrade

### Added
- AgentRuntime plugin architecture and standardized `create_agent_app()` templates.
- Unified vector database migration from ChromaDB to Milvus through `shared/infra/milvus_store.py`.
- Documentation system with ADRs and design-doc templates.

### Fixed
- CI lint cleanup: migrated 98 deprecated imports, removed Kaniko, and fixed Hadolint issues.
- Moved pip-audit and test paths into the hexagonal-architecture layout.

## [2026-03-08] - Channel Gateway Hexagonal Unification

### Added
- PM System and Channel Gateway hexagonal-architecture refactor, Phase 1 and Phase 2.
- Contract tests, split `sync_agent` conftest, and test image support.
- Docker China mirror build arguments for local development.
- China runner support and pipeline hardening.

### Changed
- Reorganized the documentation system.

## [2026-03-07] - Documentation and Architecture Normalization

### Added
- ADR-0001 through ADR-0005.
- A2A and MCP protocol support for agent-to-agent communication.
- Cloud-native Phase 1: frontend hub-and-spoke architecture, infrastructure, observability, and high availability.

### Fixed
- Full ruff lint cleanup: 421 errors across the codebase.
- Docker Compose production-grade configuration refactor.

## [2026-02-28] - PJM Agent Phase 2

### Added
- PJM Agent Phase 1/2/3 implementation:
  - Phase 1: Claude WBS task decomposition.
  - Phase 2: OpenProject writeback, Feishu approval, and Bitable sync.
  - Phase 3: assignee mapping, project filtering, and retry handling.
- Chat Agent Bitable task creation, table-management tools, and conversation context injection.
- Analysis Module report core logic and service runtime.
- Sync Module sync engine, mapper, and progress calculation.
- Scheduled daily and weekly reports to Feishu.
- Rich-card approval and rejection feedback.
- Business Prometheus metrics for all agents.

### Fixed
- Redis dedup support across multiple workers, conversation TTL, and registry SCAN.
- LLM system-prompt array format for OneAPI proxy compatibility.
- Event type normalization to `{domain}.{action}`.
- Security hardening: API-key middleware, webhook signature validation, CORS, and error redaction.

## [2026-02-25] - PM System and Frontend Refactor

### Added
- PM System with four agents: `sync_agent`, `analysis_agent`, `pjm_agent`, and `chat_agent`.
- SQLite to PostgreSQL migration script.
- Pydantic response schemas and standardized `HTTPException` handling.
- Dependency injection through `get_agent()` and async generator event loops.

### Changed
- Aligned all agents to the Wisdoverse Cell architecture standard: repository pattern and upgraded `DatabaseManager`.
- Consolidated agent Dockerfiles into a multi-target build file.

### Fixed
- Feishu v2.0 event adaptation, chat-agent forwarding, and build repair.
- `verify_signature` skip behavior when `encrypt_key` is not configured.
- Pydantic v2 migration and replacement of deprecated `datetime.utcnow()`.

## [2026-02-15] - Next.js 16 Frontend

### Added
- Complete Next.js 16 frontend implementation.
- Frontend hub-and-spoke architecture for a 26-agent fleet.

## [2026-02-13] - Cloud-Native Refactor Design

### Added
- Five-phase cloud-native refactor design: infrastructure, observability, high availability, code quality, and load testing.
- Production hardening for connection pooling, version control, middleware, and observability.

## [2026-01-28] - Initial Channel Gateway

### Added
- Multi-platform Channel Gateway.
- Feishu `lark-oapi` SDK integration replacing direct `httpx` usage.
- Moltbot plugin compatibility layer.
- E2E test infrastructure.

### Changed
- Renamed the project integration target from Moltbot to OpenClaw.

## [2026-01-27] - Gateway and Skill System

### Added
- Legacy gateway prototype, now retired.
- Skill system design.
- Docker Compose production-grade configuration.
- CI audit improvements for security, reliability, and performance.
- Kaniko replacement for Docker-in-Docker builds.

## [2026-01-23] - Feishu Deep Integration

### Added
- Feishu integration covering Bitable and Bot Commands `/list` and `/export`.
- M4 Data Dashboard UI.
- Requirement Manager Agent M4 completion.
- WeCom integration.

## [2026-01-20] - Project Foundation

### Added
- Wisdoverse Cell initialization with Docker Compose and setup scripts.
- Requirement Manager Agent M1 enterprise configuration and M2 semantic search, conflict detection, and export.
- BaseAgent integration design.
- Agent coding standards and templates.
- GitLab CI with SAST and dependency scanning.
- Renovate automated dependency updates.
