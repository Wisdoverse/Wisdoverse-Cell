# ADR-0010: Chat-Agent Runtime Extraction

- **Date**: 2026-05-22
- **Status**: Accepted (decision); implementation Stage 3 work.
- **Closes**: DDD compliance audit row DDD-016 (boundary violation); unblocks DDD-017 (conversation engine port migration).

## Context

`services/gateways/user_interaction/` is documented as a **gateway**
(per `module-boundaries.md` §2.7) but currently owns three
product-domain tables:

- `chat_agent_conversation_histories`
- `chat_agent_card_operations`
- `chat_agent_daily_progress`

Plus the gateway's own outbox `chat_agent_user_interaction_event_outbox`.

The table prefix `chat_agent_*` signals the intended owner: a dedicated
**chat-agent** runtime, not the gateway. `module-boundaries.md` §3
rule 8 (added in PR #226) forbids gateways from owning product-domain
records. Today's User Interaction Gateway carries the boundary
violation flagged as DDD-016 (high severity).

Additionally, `services/gateways/user_interaction/core/chat_service.py`
imports `shared.infra.conversation_engine` directly — the DDD-017
application-purity violation. The chat_service belongs in a runtime
that owns the chat-agent domain, not in the gateway layer.

`AGENTS.md` Part 3 rule 13 lists `chat-agent` as a canonical runtime
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
2. The chat business logic from
   `services/gateways/user_interaction/core/chat_service.py`,
   `core/daily_tasks.py`, `core/bitable_operations.py`,
   `core/ops_logger.py`, `core/tools.py`.
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
- **Agent ID already canonical**. `AGENTS.md` Part 3 rule 13 lists
  `chat-agent`; the extraction uses the reserved ID without
  introducing a new identifier.
- **Unblocks DDD-017**. The conversation-engine port lives in core/
  today (PR #246 seeds it); the port + concrete consumer move with
  the business logic into the chat-agent runtime, eliminating the
  remaining `shared.infra.conversation_engine` import.
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
  row moves from "User Interaction + Channel Gateways" to "chat-agent
  runtime".
- `module-boundaries.md` §2.7 splits: §2.7a User Interaction
  Gateway (gateway concerns only), §2.7b Channel Gateway (unchanged),
  new §2.13 Chat Agent.
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

This ADR records the **decision and sequence**. Implementation lands
in 5–7 separate PRs once the pre-conditions hold. When the first
chat-agent runtime PR lands, append a `chat-agent` row to
`agent_catalog.py` and update `module-boundaries.md` accordingly.

After the extraction completes, the DDD-016 boundary-violation
callout in `ddd-compliance-audit.md` §5.12 and the §4.8 (UIG)
scorecard are revised: dim 1 (Bounded Context) and dim 11 (ACL)
flip to ✓.
