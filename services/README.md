# Runtime Services

`services/` contains deployable runtime boundaries that are not true business
agents.

| Path | Responsibility |
|------|----------------|
| `gateways/user_interaction/` | User-facing chat and Feishu webhook gateway. |
| `gateways/channel/` | Implemented multi-channel gateway for outbound delivery events and adapter status. |
| `orchestration/coordinator/` | Cross-service event orchestration worker. |

These services may route work to agents or shared capabilities, but they should
not be presented as business agents.
