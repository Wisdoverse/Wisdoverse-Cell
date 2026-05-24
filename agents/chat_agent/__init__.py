"""Chat Agent runtime.

Destination runtime for the chat domain extracted from
`services/gateways/user_interaction/`. ADR-0010 Steps 1-7 are
represented in code for the gateway boundary: product-table metadata,
ports, use cases, persistence adapters, service composition, scheduler,
outbox dispatching, and internal HTTP APIs live here. The gateway calls
this runtime through HTTP adapters and no longer owns chat-agent
product core/db/model aliases.

Canonical runtime ID: `chat-agent` (AGENTS.md Part 3 rule 13).
"""
