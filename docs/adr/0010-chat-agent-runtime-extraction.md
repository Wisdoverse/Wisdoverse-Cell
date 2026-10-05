# ADR-0010: Chat-Agent Runtime Extraction

- **Date**: 2026-05-22
- **Status**: Accepted (decision); implementation Stage 3 work.
- **Closes**: DDD compliance audit row DDD-016 (boundary violation); unblocks DDD-017 (conversation engine port migration).

## Context

At the time this ADR was accepted, `services/gateways/user_interaction/`
was documented as a **gateway** (per `module-boundaries.md` §2.7) but owned
three product-domain tables:

- `chat_agent_conversation_histories`
- `chat_agent_card_operations`
- `chat_agent_daily_progress`

Plus the chat integration outbox that is now canonical as
`chat_agent_event_outbox`.

The table prefix `chat_agent_*` signals the intended owner: a dedicated
**chat-agent** runtime, not the gateway. `module-boundaries.md` §3
rule 8 (added in PR #226) forbids gateways from owning product-domain
records. The User Interaction Gateway carries the DDD-016 boundary risk until
ADR-0010 Steps 4-7 remove compatibility read/write paths.

Additionally, the gateway `core/chat_service.py` imported
`shared.infra.conversation_engine` directly at ADR acceptance time — the
DDD-017 application-purity violation. The chat_service belongs in a runtime
that owns the chat-agent domain, not in the gateway layer.

The [stable identifier rules](../architecture/architecture-principles.md#stable-identifiers) list `chat-agent` as a canonical runtime
identifier from the 2026-05-10 brand unification — the ID is already
reserved.

## Decision

Extract a dedicated **`chat-agent` runtime** that owns the three
product-domain tables and the conversational logic; reduce the User
Interaction Gateway to its transport + webhook-intake concerns.

### Scope

#### What moves to `agents/chat_agent/` (new)

1. The three tables and their SQLAlchemy mappings:
   - `chat_agent_conversation_histories`
   - `chat_agent_card_operations`
   - `chat_agent_daily_progress`
2. The chat business logic now under `agents/chat_agent/core/`:
   `chat_service.py`, `daily_tasks.py`, `bitable_operations.py`,
   `ops_logger.py`, and `tools.py`.
3. The ports under `core/chat_ports.py` (history store, daily
   progress, conversation-engine port from DDD-017), the
   `ApprovalGate` consumer port, and the card renderer ports.
4. `models/conversation.py`, `models/card_operation.py`,
   `models/daily_progress.py`, `models/event_outbox.py` (rename to
   `chat_agent_event_outbox`).
5. The full use-case set: `event_use_cases.py`, `request_use_cases.py`,
   `scheduler_use_cases.py`, `outbox_delivery_use_cases.py`,
   `application_facade.py`.

#### What stays in `services/gateways/user_interaction/`

1. `core/webhook_intake.py` — Feishu webhook signature + payload
   normalisation.
2. `core/webhook_processing.py` — typed inbound event creation.
3. Outbound to `chat-agent` via the EventBus (`chat.user-message`
   inbound integration event; `chat.message-rendered` outbound event
   for the gateway to push to Feishu).
4. No tables; no LLM imports; no chat business logic. The gateway
   becomes the Anti-Corruption Layer to Feishu only.

### Sequence (each step a separate PR per `architecture-principles.md` §3)

1. Create the `chat-agent` runtime skeleton under `agents/chat_agent/`
   with `create_agent_app()` + plugin shells + empty `core/domain/`
   + a `chat-agent` row in `agent_catalog.py`. No table moves yet.
2. Move the three product tables to the chat-agent runtime: copy the
   models, add an additive Alembic migration that creates duplicate
   tables in the chat-agent schema (per-runtime DB per ADR-0002 once
   Stage 4 lands; for now same DB, new owner runtime).
3. Move `chat_service.py` and the dependent core modules into
   `agents/chat_agent/core/`. Migrate the DDD-017
   `ConversationEnginePort` consumer at the same time (replaces the
   direct `shared.infra` import).
4. Cut over read paths: the User Interaction Gateway no longer reads
   `chat_agent_*` tables; gateway reads come from a chat-agent HTTP
   endpoint (`/api/v1/chat-agent/conversation/{user_id}`) or from
   integration events.
5. Cut over write paths: gateway writes are translated into inbound
   chat-agent events; chat-agent writes its own tables.
6. Drop the legacy gateway-side tables once read parity is
   established for two weeks.
7. Architecture-boundary test added: gateway runtime cannot import
   `chat_agent_*` table models or write paths.

## Rationale

- **Boundary rule already binding**. `module-boundaries.md` §3 rule 8
  states gateways must not own product-domain records. This is the
  current single open violation.
- **Agent ID already canonical**. The [stable identifier rules](../architecture/architecture-principles.md#stable-identifiers) list
  `chat-agent`; the extraction uses the reserved ID without
  introducing a new identifier.
- **Unblocks DDD-017**. The conversation-engine port moves with
  the business logic into the chat-agent runtime, eliminating direct
  `shared.infra.conversation_engine` imports from the gateway core.
- **Failure isolation**. The chat surface is the highest-traffic user
  touchpoint; keeping it inside a gateway means a chat-agent OOM
  could take down webhook intake. Extraction separates the failure
  domains.
- **Reviewable**. Each step in the sequence is one PR per the §3
  constraint. The full extraction is therefore several PRs (5–7),
  matching how the Dev / QA agents were established originally.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Keep tables in gateway, just rename | Doesn't fix the boundary violation; rule 8 still flags. |
| Move tables but keep `chat_service.py` in gateway | Splits one domain across two runtimes; harder to reason about transactions. |
| Promote `user_interaction` to a chat-agent (no separate gateway) | Loses the inbound-only Anti-Corruption Layer; the gateway concern is real (webhook signature, payload normalisation) and belongs at the boundary. |
| Defer until DDD-014 (Sync split) lands | Independent work; gateway boundary violation is the higher-severity finding (high vs. high but no dependency). Order is determined by readiness, not coupling. |

## Consequences

- New runtime directory `agents/chat_agent/` with its own deployable.
- `chat-agent` becomes the eighth real business runtime agent (the
  others remain `requirement-manager`, `pjm-agent`, `qa-agent`,
  `dev-agent`).
- 3 product tables move owner runtime (not contents); per ADR-0002
  per-agent DB isolation, the chat-agent gets its own Postgres user.
- `data-ownership.md` §2 storage inventory updated; the `chat_agent_*`
  row moves from "User Interaction + Channel Gateways" to "Chat Agent".
- `module-boundaries.md` §2.7 records the gateway boundary plus the
  `agents/chat_agent/` product runtime owner during the ADR-0010 cutover.
- Architecture-boundary tests gain a rule preventing future
  product-domain ownership inside `services/gateways/*`.

## Rollout

Stage 3 work per `migration-plan.md`. Pre-conditions:

1. PR #226 (foundation audit + sibling reconciliation) merged so the
   new rule 8 in `module-boundaries.md` §3 is live.
2. PR #246 (DDD-017 conversation-engine port seed) merged so the
   port surface the chat-agent will consume is in place.
3. Per-runtime migration story documented (already in
   `per-runtime-migrations.md`).

Rollback: each step's PR ships its own revert path. The dual-write
window in Step 5 is the cutover safety net.

## Status Tracking

This ADR records the **decision and sequence**. Steps 1-7 are now
represented in code for the gateway boundary: the chat-agent runtime
package, table metadata, persistence adapters, core use cases, runtime
service composition, scheduler, outbox dispatcher, default
Docker/runtime entrypoints, conversation/daily-progress read endpoints,
the internal `/api/v1/chat-agent/requests` boundary used by Feishu
webhook traffic, and Bitable card-operation routes live under
`agents/chat_agent/`. The user-interaction gateway app/service/webhook
path and compatibility daily-progress/Bitable API routes no longer
import the chat-agent runtime in-process; they call chat-agent APIs
through an HTTP client adapter. Legacy gateway `core/`, `db/`, and
`models/` aliases for chat-agent product state have been removed, and
architecture tests forbid production gateway imports of
`agents.chat_agent.*`.

The DDD-016 boundary-violation callout in
`ddd-compliance-audit.md` §5.12 and the §4.8 (UIG) scorecard are
revised accordingly: dim 1 (Bounded Context) and dim 11 (ACL) are no
longer blocked by gateway ownership of chat-agent product state.
