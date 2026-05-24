# User Interaction Gateway

Inbound user-interaction gateway. Receives chat traffic and Feishu
webhook payloads, normalizes external transport details, and proxies
chat-domain requests to the `chat-agent` runtime.

Runtime ID: `user-interaction-gateway`.
See [`docs/architecture/module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.7.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `services/gateways/user_interaction/` |
| Owned data | None. `chat_agent_*` models/adapters live under `agents/chat_agent/`. |
| Owned outbox | None for chat-agent product events. `chat_agent_event_outbox` is owned and dispatched by `agents/chat_agent/`. |
| Aggregate root | None — gateway boundary. Product-domain modeling lives in the chat-agent runtime. |
| Application purity gap | Closed for this gateway: chat-service implementation, runtime composition, persistence, scheduler, and outbox dispatching live under `agents/chat_agent/`. |
| Inbound entry | `core/webhook_intake.py` `FeishuWebhookMessage`; webhook chat requests call the chat-agent internal request API through `adapters/chat_agent_client.py`. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Webhook intake** | The Feishu webhook entry path that turns an external HTTP callback into a typed inbound event. |
| **Conversation history** | Per-user chat record owned by `agents/chat_agent/`. |
| **Card operation** | An interactive Feishu card lifecycle record (`pending` / `success` / `failed` etc.). |
| **Daily progress** | The end-of-day status snapshot pushed to users. |
| **Conversation engine** | The LLM-backed conversational tool runtime consumed through the chat-agent `ConversationEngineFactory` port. |
| **Tool execution event** | An LLM tool-call result recorded for downstream observability. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.7:

- **Upstream**: Anti-Corruption Layer to external users via Feishu / WeCom adapters.
- **Downstream**: Anti-Corruption Layer to `chat-agent` HTTP APIs for chat-domain requests.
- **No product ownership**: conversation history, card operations, daily progress, scheduler jobs, and durable outbox dispatching belong to `agents/chat_agent/`.

## Architecture

```
core/
  webhook_intake.py         Feishu webhook entry; FeishuUserDirectoryPort Protocol
  webhook_processing.py     parsed payload → chat-agent HTTP request
  card_ports.py             gateway-local reply-card renderer port
adapters/chat_agent_client.py HTTP adapter to `/api/v1/chat-agent/requests`
api/bitable.py              compatibility HTTP proxy to chat-agent Bitable API
api/daily_progress.py       compatibility HTTP proxy to chat-agent daily-progress API
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.8 — Interaction Gateway.

## Outstanding Boundary Work

The DDD-016 / DDD-017 code boundary is closed for the gateway:

- The gateway no longer imports `agents.chat_agent.*` from production app,
  API, service, adapter, core, db, or model code.
- The gateway keeps only transport, webhook intake, outbound card delivery,
  and chat-agent HTTP client adapters.
