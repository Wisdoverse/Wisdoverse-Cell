# Requirement Manager

Real business runtime agent that turns user intent and meeting transcripts
into structured requirements. Owns the PRD flow and the feedback-learning
loop.

Canonical agent ID: `requirement-manager`.
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.2 for the bounded context catalog entry.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/requirement_manager/` |
| Owned tables | `meetings`, `requirements`, `open_questions`, `feedback_records`, `llm_usage`, `chat_messages`, `requirement_event_outbox` |
| Aggregate root | `Requirement` (`core/domain/requirement.py:52-101`) |
| Typed identities | `RequirementId`, `MeetingId`, `OpenQuestionId`, `FeedbackRecordId` from `shared/core/identifiers.py` |
| State machine | `core/domain/lifecycle/requirement_states.py:31-36` `VALID_TRANSITIONS` table; `Requirement.transition_to()` enforces and raises `InvalidRequirementTransitionError` on illegal moves |
| Domain events | `RequirementStatusChanged` raised by aggregate; drained by use case and persisted to outbox |
| Unit of work | `core/unit_of_work_ports.py` `RequirementUnitOfWork` Protocol |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Meeting** | A captured discussion artifact (audio, transcript, summary) ingested through Feishu or other channels. Source of raw user intent. |
| **Requirement** | A structured, persistent record of a user need extracted from one or more meetings. Has a lifecycle (`pending → confirmed → changed → rejected`) and links back to its source `meeting_id`s. |
| **Open Question** | A clarification request raised against a Requirement; flows back to the user for resolution. |
| **Feedback Record** | A user's reaction to an extracted Requirement; drives the feedback-learning loop that improves extraction prompts. |
| **PRD** | Product Requirements Document — composed view of confirmed Requirements with their OpenQuestions resolved. |
| **Confirmation** | Explicit user acknowledgement that a Requirement matches their intent. Transitions Requirement to `confirmed`. |
| **Rejection** | Explicit user denial that a Requirement matches their intent. Transitions Requirement to `rejected` with a reason. |
| **Status change** | A domain event raised by `Requirement.transition_to()` whenever the lifecycle moves between states. |

Cross-link to the company-wide vocabulary:
[`docs/overview/glossary.md`](../../docs/overview/glossary.md).

## Domain Services

| Service / policy | File | Owns |
|------------------|------|------|
| `RequirementExtractionMaterializer` | `core/domain/extraction_materialization.py` | Extractor-result traversal, source-meeting association, requirement drafts, and open-question assignment before persistence. |
| `RequirementExtractionPublicationPolicy` | `core/domain/extraction_materialization.py` | Published-language extraction evidence after persistence: `requirement.extracted` payload and search-index document shape. |
| `RequirementFeedbackLearningPolicy` | `core/domain/feedback_learning.py` | Correction/rejection classification, changed-field calculation, and rejection placeholder values for feedback learning. |
| `RequirementAggregateConsistencyPolicy` | `core/domain/aggregate_consistency.py` | Declared immediate-consistency write scopes for meeting ingest, Requirement lifecycle mutations, feedback evidence, question answers, outbox staging, and post-commit side effects. |

## Consistency Boundaries

Requirement Manager uses explicit UoW-backed consistency scopes:

- `meeting_ingest`: primary aggregate `Meeting`; same transaction may materialize derived `Requirement`, `OpenQuestion`, and `RequirementEventOutbox` rows because they come from one extraction source and must become visible atomically.
- `requirement_lifecycle_mutation`: primary aggregate `Requirement`; same transaction may include `FeedbackRecord` learning evidence and `RequirementEventOutbox` rows for the same operator decision.
- `question_answer`: primary aggregate `OpenQuestion`; no cross-aggregate writes.

Vector indexing and notifications are post-commit side effects.

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.2:

- **Upstream**: Anti-Corruption Layer to Interaction Gateway and Feishu via `shared/integrations/feishu/`; Anti-Corruption Layer to LLM Gateway extraction responses via `core/llm_extraction_response.py`.
- **Downstream**: Customer/Supplier to PJM Agent (emits `requirement.*` integration events; PJM is the primary consumer).
- **Conformist to Control Plane** on `AgentRun`, `AuditEvent` Published Language.

## Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `meeting.uploaded` | Subscribe | New meeting transcript ingested |
| `project.created`, `project.updated`, `sprint.started`, `sprint.completed` | Subscribe | Lifecycle hooks from PJM / Coordinator |
| `coordinator.dispatch` | Subscribe | Dispatch envelope from Coordinator |
| `requirement.*` | Publish | Requirement lifecycle integration events |

Event payloads live in `shared/schemas/event_payloads.py`; the Event Catalog at
[`docs/guides/event-catalog.md`](../../docs/guides/event-catalog.md) is the
authoritative list.

## API

See [`docs/guides/api-reference.md`](../../docs/guides/api-reference.md) for
the operator-facing Requirement REST surface and gRPC `HealthCheck`. Card
flow runs through Feishu via the agent-local renderer in `adapters/`.

## Development

```bash
make dev      # uvicorn --reload on the requirement manager agent
pytest agents/requirement_manager/tests/ -v
```

## Architecture

Layered per `architecture-principles.md`:

```
api/        FastAPI routers — thin handlers
app/        create_agent_app() wiring + outbox dispatcher plugin
core/
  application_facade.py — composes use cases for the service shell
  domain/   Requirement aggregate + state machine
  *_use_cases.py — orchestration only; depends on ports
  *_ports.py — outbound port interfaces
db/         SQLAlchemy stores; returns domain models
adapters/   External SDK / HTTP clients (e.g. Feishu cards)
service/    BaseAgent subclass
models/     Pydantic DTOs
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../docs/architecture/ddd-compliance-audit.md) §4.2.
