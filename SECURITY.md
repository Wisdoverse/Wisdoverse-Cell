# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |
| feat/*  | Development only |
| intern-archive | No - historical internal archive only |

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public issue
2. Email: security@wisdoverse.ai
3. Include: description, reproduction steps, impact assessment
4. Expected response: within 48 hours

## Security Architecture

### Authentication & Authorization
- **External**: Feishu/WeCom webhook signature verification; Feishu signature
  verification fails closed if `FEISHU_ENCRYPT_KEY` is missing while signature
  verification is enabled.
- **Internal**: `X-Internal-Key` header between services (HMAC comparison)
- **Database**: Per-agent PostgreSQL users with table-level GRANT
- **Redis**: Password authentication + per-agent db isolation

### Data Protection
- **PII Handling**: open_id hashed in logs, never in LLM prompts
- **Data Residency**: `REQUIRE_ANTHROPIC_PROXY=true` enforces approved proxy
- **DSAR**: Data Subject Access Request API (详见下方 DSAR 章节)
- **Transport**: External TLS should terminate at the reverse proxy or platform
  ingress. Internal Compose gRPC traffic runs on the private backend network by
  default; use mTLS or a service mesh before carrying internal traffic over an
  untrusted network.
- **Encryption**: Database encryption at rest should be enforced by the
  production PostgreSQL platform.

### LLM Security
- **Prompt Injection**: XML delimiter isolation for user input
- **Tool Permissions**: send_feishu_message restricted to self (non-admin)
- **Budget Control**: Redis-based daily cost metering with auto-downgrade
- **Circuit Breaker**: Prevents cascade failures on API outage

### Infrastructure
- **Containers**: Non-root user, read-only filesystem where possible
- **Secrets**: Environment variables (Docker Secrets in production)
- **Network**: Backend network is internal-only
- **Monitoring**: 51 Prometheus alert rules including security alerts

## DSAR (数据主体访问请求)

符合 GDPR / PIPL 要求，提供数据主体权利请求处理能力。

### 支持的操作

| 操作 | 端点 | 说明 |
|------|------|------|
| 数据查询 | `POST /api/dsar/export` | 导出用户所有数据 (JSON) |
| 数据删除 | `POST /api/dsar/delete?confirm=true` | 删除/匿名化用户数据 |
| 删除预检 | `POST /api/dsar/delete` | dry-run 预检受影响记录 |

### 数据范围

DSAR 请求覆盖以下数据源：

- **Chat Agent**: 聊天记录、用户偏好
- **PJM Agent**: 任务分配记录、审批记录
- **Sync Agent**: 同步日志中的用户关联数据
- **Requirement Manager**: 需求提取中的用户上下文

### 处理流程

1. 每个 Agent 挂载自己的 `shared.api.dsar_router`
2. Agent 通过本地 `DSARService` 和 `DSARHandler` 导出或删除本服务持有的数据
3. 删除默认 dry-run，必须显式传入 `confirm=true` 才会执行写操作
4. 运营方汇总各 Agent 处理结果，30 天内响应请求人

### 数据保留

| 数据类型 | 保留期限 | 说明 |
|----------|----------|------|
| 聊天记录 | 90 天 | 到期自动归档 |
| 审计日志 | 365 天 | 法律合规要求 |
| LLM 调用日志 | 30 天 | 仅保留元数据，不含 prompt 内容 |
| 事件队列 | 24 小时 | Redis Streams TTL |

## LLM 数据出境合规

### 代理管控

```bash
# .env 配置 — 强制通过合规代理访问 Claude API
REQUIRE_ANTHROPIC_PROXY=true
ANTHROPIC_BASE_URL=https://claude-proxy.example.com/v1
```

- 启用 `REQUIRE_ANTHROPIC_PROXY=true` 时，`LLMGateway` 启动检查 `ANTHROPIC_BASE_URL` 是否为合规代理地址
- 若未配置或指向官方 API，启动时抛出异常阻止服务运行
- 代理服务器负责日志记录、数据脱敏、地域管控

### LLM Prompt 安全

- **禁止传入 PII**: `open_id`、手机号、邮箱等不得进入 LLM prompt
- **XML Delimiter 隔离**: 用户输入用 `<user_input>` 标签隔离，防止 prompt 注入
- **AI 内容标识**: Agent 生成的内容标注 "AI 生成，仅供参考"
- **输出过滤**: 系统 prompt 和内部信息不得在回复中泄露

## Dependency Management

- Python: `requirements.txt` with `scripts/lock-deps.sh` for reproducible builds
- Go: `go.sum` for integrity verification
- Regular dependency updates via CI scanning
