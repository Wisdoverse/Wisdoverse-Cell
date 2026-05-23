# Chat Agent

Destination runtime for the chat domain currently held by the
User Interaction Gateway. ADR-0010 records the extraction
sequence; this directory is the **Stage 3 Step 1 skeleton** —
package shape only; tables, ports, and use cases migrate in
follow-up PRs.

Canonical runtime ID: `chat-agent` (AGENTS.md Part 3 rule 13).
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md)
§2.7 for the gateway → chat-agent boundary that this runtime
materializes.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/chat_agent/` |
| Status | **Skeleton** — no tables or business logic yet (per ADR-0010 Step 1). |
| Owned tables | `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress` (move in Step 2 of ADR-0010). |
| Aggregate root | TBD — promoted alongside the `chat_service.py` migration in Step 3. |
| ACL ports | `ConversationEnginePort` (already shipped under DDD-017 in `services/gateways/user_interaction/core/chat_ports.py`; moves here in Step 3). |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Conversation turn** | One user message + the assistant's response in the chat session. |
| **Conversation history** | Persisted multi-turn context, owned by the chat-agent. |
| **Card operation** | A typed Feishu card update triggered by the agent (e.g. status update, approval prompt). |
| **Daily progress** | A periodic per-user summary computed by the agent. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md):

- **Upstream from `services/gateways/user_interaction/`**: receives `chat.user-message` integration events normalised by the gateway's webhook layer.
- **Downstream to `services/gateways/user_interaction/`**: emits `chat.message-rendered` events for the gateway to push back to Feishu.
- **ACL** to LLM via `ConversationEnginePort` (DDD-017) + `shared.infra.llm_gateway` (lands in Step 3).
- **Conformist** to Control Plane (per the standard runtime contract).

## Architecture

```
agents/chat_agent/
  __init__.py            runtime package
  README.md              this file
  app/
    main.py              FastAPI entry via create_agent_app
  service/
    agent.py             ChatAgent BaseAgent subclass (no-op until Step 3)
  core/
    __init__.py
    domain/              empty — aggregates land here per ADR-0010 Step 3
```

## ADR-0010 sequence (this runtime)

1. **Skeleton (this PR)** — package shape + `ChatAgent` skeleton with no event subscriptions.
2. Add chat tables + models + Alembic migration (additive; gateway tables stay dual-written during cutover).
3. Migrate `chat_service.py` + related use cases from the gateway into `agents/chat_agent/core/`.
4. Cut over reads (gateway begins emitting `chat.user-message` to the new runtime).
5. Cut over writes (gateway stops touching the chat tables).
6. Drop legacy `chat_agent_*` tables under the gateway schema.
7. Add a boundary test that forbids `services/gateways/user_interaction/` from importing `chat_*` modules.

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../docs/architecture/ddd-compliance-audit.md)
row DDD-016 (high severity) + DDD-017 (gateway purity).
