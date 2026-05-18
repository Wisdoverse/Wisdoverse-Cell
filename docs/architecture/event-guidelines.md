# Event Guidelines

Last updated: 2026-05-18

Status: Foundation document.

This document is the contract every new or modified event must follow. It
applies to two distinct event categories:

1. **Domain events** — internal to one boundary, never published to the
   EventBus. They exist to compose aggregate behavior inside a runtime.
2. **Integration events** — published through the EventBus across runtime
   boundaries. They are part of the public contract.

The current implementation map lives in
[`docs/guides/event-catalog.md`](../guides/event-catalog.md). This document
defines the rules that catalog must conform to.

---

## 1. Domain Events

1. Domain events live inside `agents/<a>/core/domain/` (or the equivalent
   for the control plane and capabilities).
2. They are plain Python dataclasses or Pydantic models with no
   serialization concerns.
3. Aggregates emit domain events as part of state transitions. Use cases
   collect them and decide whether any of them must be promoted to an
   integration event before write commit.
4. Domain events do not cross runtime boundaries. They are never
   published to the EventBus directly. Promotion to an integration event
   is an explicit step.

---

## 2. Integration Events

### 2.1 Envelope

Every integration event uses the standard envelope:

```python
Event(
    event_id="evt_{ulid}",
    event_type="{domain}.{action}",
    source_agent="<runtime-id>",
    payload={...},
    schema_version="1.0",
    metadata={
        "trace_id": "<X-Trace-ID>",
        "correlation_id": "<optional>",
        "retry_count": 0,
    },
)
```

Rules:

1. `event_id` is stable and uses the `evt_` prefix; ULIDs from
   `shared.core.ids` are the canonical generator.
2. `event_type` uses `{domain}.{action}` lowercase past-tense
   (`requirement.extracted`, `dev.workflow-completed`).
3. `source_agent` is the publishing runtime ID (`requirement-manager`,
   `pjm-agent`, etc.).
4. `payload` is JSON-serializable. The Pydantic model lives in
   `shared/schemas/event_payloads.py`.
5. `schema_version` is mandatory. Bump on backward-incompatible payload
   change.
6. `metadata.trace_id` propagates the originating request's trace.

### 2.2 Producer Contract

1. The producing runtime owns the event in the Event Catalog row.
2. The producing runtime writes the event to its own `*_event_outbox`
   inside the same transaction as the state change that justifies it.
3. The runtime plugin `OutboxDispatcherPlugin` publishes from outbox to
   the EventBus. Producers never publish directly.
4. New events must be added to:
   (a) `shared/schemas/event_payloads.py` (Pydantic model);
   (b) `docs/guides/event-catalog.md` (row);
   (c) a producer/consumer contract test under `tests/contract/events/`.

### 2.3 Consumer Contract

1. Consumers join one Redis Streams consumer group per consumer purpose
   (`<consumer>.<event_type>`).
2. Consumers are idempotent. Replays of the same `event_id` produce the
   same observable result.
3. Consumers declare a domain idempotency key (in addition to `event_id`)
   when the event triggers a state change that has a natural business key.
4. Consumer failures classify into the documented categories (network,
   auth, rate-limit, overload, content-size, internal). The classification
   determines retry behavior.
5. After exhausting retries, the event lands on `dlq.failed` with a
   classified reason. Operators inspect the DLQ; replays go through an
   operator command.

### 2.4 Schema Evolution

1. Add fields → backward-compatible. Keep `schema_version` the same. Update
   the Event Catalog row.
2. Remove or rename fields → bump `schema_version` to the next major. Run
   producer and consumer side-by-side until the old `schema_version` is
   retired.
3. Repurposing an event type is forbidden. Create a new event type.

---

## 3. Naming Conventions

- `event_type`: `<domain>.<past-tense-verb>` with hyphens inside the verb
  (`pm.decompose-completed`, `qa.acceptance-failed`). Avoid noun-only
  names.
- `event_id`: `evt_<ulid>`.
- `trace_id`: `tr_<ulid>` propagated end-to-end.
- Consumer group: `<consumer-name>.<event-type>`.
- Outbox table: `<runtime>_event_outbox` (canonical) or
  `<runtime>_agent_event_outbox` (legacy alias for some runtimes).

---

## 4. Domain Catalog Pointer

The current per-domain event matrix lives in
[`docs/guides/event-catalog.md`](../guides/event-catalog.md). Domains
include (non-exhaustive):

- requirement
- sync
- report
- analysis
- pm
- chat
- coordinator
- task
- a2a
- channel
- qa
- dev

When a new domain is added, this document is updated alongside the
catalog.

---

## 5. Idempotency and Retries

1. Idempotency keys are domain-natural where possible. For example,
   `qa.acceptance-completed` uses the acceptance run ID as the natural
   key.
2. Producers retry through the outbox dispatcher; consumers retry through
   the consumer group's backoff.
3. Maximum retry count is bounded. After bounding, the DLQ takes over.
4. Re-publishing the same `event_id` is allowed and expected; consumers
   must treat it as no-op.

---

## 6. Failure Handling

1. Outbox writes record `status`, `retry_count`, `attempts`, `last_error`,
   `created_at`, `published_at`.
2. Failed publish attempts log a classified reason. The dispatcher's
   health check reports total / published / failed counts.
3. DLQ entries are observable through the operator dashboard. Operators
   trigger replay through a documented command, not by manipulating Redis
   directly.

---

## 7. Documentation

1. The Event Catalog row is mandatory in the PR that introduces the event.
2. Per-event producer/consumer contract tests are mandatory in the same
   PR.
3. Event payload changes update the `schema_version` and the catalog row
   together.

---

## 8. Forbidden Patterns

- Direct publish to the EventBus from application code (bypassing the
  outbox).
- A consumer that mutates database state without an idempotency key.
- An integration event that carries raw secrets, tokens, or PII.
- An integration event that is "internal but published anyway" — promote
  it explicitly to an integration event with a catalog row, or keep it
  domain-only.
- A new event without a Pydantic model and a catalog row.

---

## 9. Maintenance

When this document changes:

- Update `docs/guides/event-catalog.md`.
- Update `shared/schemas/event_payloads.py` for any new payload models.
- Update `tests/unit/test_architecture_boundaries.py` if a new structural
  rule applies (e.g., catalog ↔ schema model match).
