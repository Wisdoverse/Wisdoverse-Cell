# ADR-0005: Channel Gateway 六边形统一架构

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

## Status
已采纳 (2026-03-08)

## Context
系统中存在三套重叠的 channel 体系:
- `shared/services/channels/` — 底层 channel 抽象
- `shared/services/gateway/` — 入站消息网关
- `shared/services/channel_gateway/` — 出站 adapter 框架

这导致了 import 混乱、类型重复定义、以及难以测试的交叉依赖。

## Decision
统一为六边形架构 (Hexagonal Architecture)，按职责分层:

- **`shared/core/messaging/`** — Port 接口层 (PlatformAdapter, UnifiedMessage, AdapterRegistry)
- **`shared/messaging/inbound/`** — 入站网关 (原 gateway/)
- **`shared/messaging/outbound/`** — 出站 adapter + DeliveryService (原 channel_gateway/)
- **`shared/integrations/{feishu,wecom,openclaw,openproject}/`** — 平台 SDK wrapper
- **`shared/integrations/channels/`** — Channel 抽象层
- **`shared/infra/`** — 横切基础设施 (CircuitBreaker, AgentClient)

迁移策略: 原文件转为 compat re-export stub，实现零消费者变更的渐进式迁移。

## Consequences

### Positive
- 依赖方向清晰: core → messaging → integrations
- Port/Adapter 模式支持独立测试每个 adapter
- DeliveryService 提供安全广播 (semaphore + return_exceptions)
- CI lint 拦截新的 deprecated import，防止回退
- Feature flag (`use_new_delivery_service`) 支持灰度上线

### Negative
- 需维护 74 个 compat re-export 文件，待消费者迁移后移除
- 消费者代码中仍有 229 处 legacy import (由 `migration_metrics.sh` 追踪)

### Neutral
- 对现有消费者完全透明，compat stub 保证 import 路径不变
