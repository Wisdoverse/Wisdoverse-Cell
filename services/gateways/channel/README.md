# Channel Gateway

`services/gateways/channel/` is the runtime boundary for `channel-gateway`, the
multi-channel messaging gateway.

It owns the `BaseAgent` wrapper, FastAPI app, lifecycle, and event dispatch for
channel ingress/egress. Reusable messaging adapters, events, models, and
delivery primitives remain under `shared/messaging/outbound/`.

This is not a business agent and must not be moved under `agents/`.

## Bounded Context

Channel Gateway is a transport gateway, not a product-owning business context.
It owns channel delivery orchestration, adapter lifecycle, and the
`channel_gateway_event_outbox` infrastructure table. Product records such as
conversation history, card operations, daily progress, requirements,
decompositions, tasks, and acceptance runs remain in their owning runtime
contexts.

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| Channel message | A `channel.message.outbound` request produced by another runtime and delivered by the gateway. |
| Channel adapter | A platform-specific outbound adapter registered with the gateway. |
| Provider ACL | The gateway-local translation boundary that converts outbound delivery attempts and provider failures into `DeliveryResult`. Implemented by `core/provider_acl.py` `ChannelProviderACL`. |
| Delivery result | The published-language result of one outbound delivery attempt. |
| Outbox row | A durable gateway infrastructure record staged before external EventBus publish. |
| Outbox lifecycle | The guarded retry/publish state for an outbox row, enforced by `ChannelGatewayOutboxLifecycle`. |

## Context-Map Relationships

- **Open-Host Service**: Channel Gateway accepts the published
  `channel.message.outbound` event contract from runtime agents and emits
  `channel.message.delivered` results.
- **Customer/Supplier**: Dev Agent, Coordinator, chat-agent, and other runtime
  producers depend on the gateway's outbound delivery contract.
- **Anti-Corruption Layer**: `ChannelProviderACL` translates gateway delivery
  requests, missing adapter cases, and provider exceptions into the
  `DeliveryResult` published language before the event use case emits
  `channel.message.delivered`. Concrete platform adapters still own the
  channel-specific API calls.
- **Conformist**: The gateway conforms to shared outbound messaging payloads in
  `shared.messaging.outbound.models` and must not redefine those event schemas
  locally.
