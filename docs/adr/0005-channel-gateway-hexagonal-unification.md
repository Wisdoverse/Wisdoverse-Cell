# ADR-0005: Channel Gateway Hexagonal Unification

## Status

Accepted on 2026-03-08.

## Context

The messaging layer previously had three overlapping channel systems:

- `shared/services/channels/` for low-level channel abstractions.
- `shared/services/gateway/` for inbound message gateway behavior.
- `shared/services/channel_gateway/` for outbound adapter behavior.

That overlap caused import ambiguity, duplicated type definitions, and
cross-dependencies that were hard to test independently.

## Decision

Use a hexagonal messaging architecture with clear ownership boundaries:

- `shared/core/messaging/`: port interfaces such as `PlatformAdapter`,
  `UnifiedMessage`, and `AdapterRegistry`.
- `shared/messaging/inbound/`: inbound gateway orchestration.
- `shared/messaging/outbound/`: outbound adapters and `DeliveryService`.
- `shared/integrations/{feishu,wecom,openclaw,openproject}/`: platform SDK
  wrappers and platform-specific adapters.
- `shared/integrations/channels/`: channel abstraction helpers.
- `shared/infra/`: cross-cutting infrastructure such as `CircuitBreaker` and
  `AgentClient`.

Legacy import paths are migrated through compatibility re-export stubs so
consumers can move incrementally without a flag-day rewrite.

## Consequences

Positive outcomes:

- Dependency direction is clearer: core ports -> messaging orchestration ->
  platform integrations.
- Port/adapter boundaries make each adapter easier to test.
- `DeliveryService` provides safer broadcast behavior through semaphore limits
  and `return_exceptions` handling.
- CI deprecated-import checks prevent new code from returning to old paths.
- `settings.use_new_delivery_service` provides a rollout and rollback switch.

Costs and follow-up work:

- Compatibility stubs must remain until remaining consumers have migrated.
- Legacy imports should be tracked and removed once no consumers depend on them.

Neutral impact:

- Existing consumers remain operational during migration because compatibility
  stubs preserve import paths.
