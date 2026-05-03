# Gateway Agents

Gateway agents own user-facing or platform-facing ingress. They translate
external traffic into control-plane requests, EventBus events, or typed HTTP
calls to runtime modules.

Gateway packages may depend on shared ports, shared integration clients, and
control-plane API contracts. They must not import capability or orchestration
service internals directly.

## Packages

| Package | Responsibility |
|---------|----------------|
| `user_interaction/` | Direct user interaction and Feishu webhook gateway. |
| `channel/` | Multi-channel gateway for `channel.message.outbound` delivery through registered adapters. |

Gateway agents are `integration_gateway` runtime modules in the agent catalog.
