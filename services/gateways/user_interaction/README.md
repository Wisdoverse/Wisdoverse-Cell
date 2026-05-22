# User Interaction Gateway

Inbound user-interaction gateway. Receives chat traffic and Feishu
webhook payloads, classifies intent, and routes either to the
coordinator or directly to a target runtime agent.

Canonical runtime ID: `chat-agent` (legacy from earlier consolidation).
See [`docs/architecture/module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.7.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `services/gateways/user_interaction/` |
| Owned data **(violation — DDD-016)** | `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress`. Naming prefix `chat_agent_*` flags these as product-domain records, not gateway concerns; DDD-016 moves them into a dedicated `chat-agent` runtime. |
| Owned outbox | `chat_agent_user_interaction_event_outbox` |
| Aggregate root | None — gateway boundary. Product-domain modeling is deferred to the chat-agent extraction (DDD-016). |
| Application purity gap | `core/chat_service.py` imports `shared.infra.conversation_engine` directly; DDD-017 wraps it behind a port. |
| Inbound entry | `core/webhook_intake.py` `FeishuWebhookMessage`; `core/chat_service.py` chat surface. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Webhook intake** | The Feishu webhook entry path that turns an external HTTP callback into a typed inbound event. |
| **Conversation history** | Per-user chat record. Today persisted by the gateway; ownership belongs to the future chat-agent (DDD-016). |
| **Card operation** | An interactive Feishu card lifecycle record (`pending` / `success` / `failed` etc.). |
| **Daily progress** | The end-of-day status snapshot pushed to users. |
| **Conversation engine** | The LLM-backed conversational tool runtime in `shared.infra.conversation_engine`. Today imported directly; DDD-017 introduces a port at the core seam. |
| **Tool execution event** | An LLM tool-call result recorded for downstream observability. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.7:

- **Upstream**: Anti-Corruption Layer to external users via Feishu / WeCom adapters.
- **Downstream**: Conformist to Coordinator and chat-agent target on event payloads.
- **Current violation**: owns product-domain tables (DDD-016) and imports infrastructure into core (DDD-017).

## Architecture

```
core/
  application_facade.py     composes use cases for the service shell
  webhook_intake.py         Feishu webhook entry; FeishuUserDirectoryPort Protocol
  webhook_processing.py     parsed payload → inbound event
  chat_service.py           chat surface (CURRENTLY imports shared.infra.conversation_engine — DDD-017)
  bitable_operations.py     Feishu Bitable inbound flow
  daily_tasks.py            morning / evening routine domain services
  chat_ports.py             ChatHistoryStore Protocol
  event_ports.py            UserInteractionEventOutboxStore
  approval_ports.py
  request_use_cases.py / event_use_cases.py / scheduler_use_cases.py
  outbox_delivery_use_cases.py
  ops_logger.py
  tools.py                  LLM tool wiring (currently leaks SDK — DDD-017)
db/                         SQLAlchemy stores (Conversation, CardOperation, DailyProgress — DDD-016 moves these out)
models/                     Pydantic DTOs
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.8 — Interaction Gateway.

## Outstanding Boundary Work

Two open high-severity audit rows specifically apply to this gateway:

- **DDD-016**: move `chat_agent_*` product tables and their use cases into a dedicated `chat-agent` runtime. The gateway should keep only transport, webhook intake, and outbound card delivery.
- **DDD-017**: wrap `shared.infra.conversation_engine` behind a port consumed by `chat_service.py`; remove the infrastructure import from `core/`.

Until both land, this gateway intentionally owns product-domain records.
