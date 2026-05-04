# Channel Gateway

`services/gateways/channel/` is the runtime boundary for `channel-gateway`, the
multi-channel messaging gateway.

It owns the `BaseAgent` wrapper, FastAPI app, lifecycle, and event dispatch for
channel ingress/egress. Reusable messaging adapters, events, models, and
delivery primitives remain under `shared/messaging/outbound/`.

This is not a business agent and must not be moved under `agents/`.
