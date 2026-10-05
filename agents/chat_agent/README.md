# Chat Agent

Destination runtime for the chat domain extracted from the User
Interaction Gateway. ADR-0010 records the extraction sequence. Steps
1-7 are now represented in code for the gateway boundary: table
metadata, persistence adapters, chat/core use cases, service/runtime
composition, scheduler, outbox dispatcher, and internal HTTP APIs live
under `agents/chat_agent/`. Gateway app/API paths call this runtime
through HTTP adapters; legacy gateway core/db/model aliases have been
removed.

Canonical runtime ID: `chat-agent`. See [stable identifiers](../../docs/architecture/architecture-principles.md#stable-identifiers).
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md)
§2.7 for the gateway → chat-agent boundary that this runtime
materializes.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/chat_agent/` |
| Status | **ADR-0010 Steps 3-7 code path complete for the gateway boundary** — chat/core use cases, persistence adapters, runtime service composition, scheduler, outbox dispatcher, conversation read API, daily-progress read API, internal request API, and Bitable card-operation API live here; gateway app/API paths call through HTTP adapters. |
| Owned tables | `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress`, `chat_agent_event_outbox`. |
| Aggregate roots | `ConversationTranscript` in `core/domain/conversation.py` owns persisted conversation-history trimming and tool-replay safety; `CardOperationLogEntry` in `core/domain/card_operation.py` owns card-operation result vocabulary, snapshot extraction, and log events; `DailyProgressEntry` in `core/domain/daily_progress.py` owns the daily-progress status FSM and domain-event buffer. |
| ACL ports | `ConversationEnginePort` and `ConversationEngineFactory` in `agents/chat_agent/core/chat_ports.py`. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Conversation turn** | One user message + the assistant's response in the chat session. |
| **Conversation history** | Persisted multi-turn context, owned by the chat-agent. |
| **Conversation transcript** | One user's persisted chat history; history-size and leading tool-result replay invariants are guarded by the `ConversationTranscript` aggregate. |
| **Card operation** | A typed Feishu card update triggered by the agent (e.g. status update, approval prompt). |
| **Card operation log entry** | One persisted card-operation audit record; result normalization, failure-message requirement, assignee extraction, and snapshot serialization are guarded by the `CardOperationLogEntry` aggregate. |
| **Daily progress** | A periodic per-user summary computed by the agent. |
| **Daily progress entry** | One user's status update for one task on one date; status transitions are guarded by the `DailyProgressEntry` aggregate. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md):

- **Upstream from `services/gateways/user_interaction/`**: receives webhook chat requests through the internal `/api/v1/chat-agent/requests` HTTP boundary.
- **Downstream to `services/gateways/user_interaction/`**: gateway owns Feishu webhook/card transport concerns; chat-agent owns product records and command handling.
- **ACL** to LLM via `ConversationEnginePort` / `ConversationEngineFactory`; concrete engine construction is bound in `service/agent.py`.
- **Conformist** to Control Plane (per the standard runtime contract).

## Architecture

```
agents/chat_agent/
  __init__.py            runtime package
  README.md              this file
  app/
    main.py              FastAPI entry via create_agent_app
  api/                   internal chat-agent HTTP routes for request dispatch, conversation, daily-progress, and Bitable card operations
    plugins/             chat-agent outbox dispatcher
  service/
    agent.py             ChatAgent BaseAgent subclass
  core/
    __init__.py
    chat_service.py      chat turn orchestration and tool loop
    tools.py             chat-agent tool definitions and handlers
    bitable_operations.py confirmed Bitable card operation use cases
    daily_tasks.py       morning / evening routine use cases
    application_facade.py request/event/outbox/health composition
    request_use_cases.py
    event_use_cases.py
    outbox_delivery_use_cases.py
    scheduler_use_cases.py
    domain/
      card_operation.py  CardOperationLogEntry aggregate + result vocabulary
      conversation.py    ConversationTranscript aggregate + history trimming invariants
      daily_progress.py  DailyProgressEntry aggregate + status FSM
  db/
    repository.py        chat-agent table repositories
    *_store.py           SQLAlchemy adapters for chat-agent ports
```

## ADR-0010 sequence (this runtime)

1. **Done** — package shape + `ChatAgent` skeleton with no event subscriptions.
2. **Done** — chat tables + models + Alembic migration (additive; gateway tables stay dual-written during cutover).
3. **Done in code on this branch** — migrate `chat_service.py` + related use cases and runtime composition from the gateway into `agents/chat_agent/`.
4. **Done in code on this branch** — chat-agent exposes `/api/v1/chat-agent/conversation/{user_id}`, `/api/daily-progress`, and `/api/v1/chat-agent/requests`; the Feishu webhook path calls chat-agent through the HTTP client adapter.
5. **Done in code on this branch** — `/api/bitable/*` card-operation routes, scheduled daily actions, and the chat-agent outbox dispatcher live under `agents/chat_agent/`; gateway Bitable routes are HTTP proxies.
6. **Done in code on this branch** — legacy gateway `core/`, `db/`, and `models/` compatibility aliases for chat-agent product state have been removed.
7. **Done in code on this branch** — architecture tests forbid production `services/gateways/user_interaction/` imports of `agents.chat_agent.*`.

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../docs/architecture/ddd-compliance-audit.md)
row DDD-016 (high severity) + DDD-017 (gateway purity).
