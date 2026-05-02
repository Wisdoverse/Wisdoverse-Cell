# Wisdoverse Cell Operations Manual

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **版本**: v2026.05 | **标准**: Google SRE Runbook | **维护**: Platform Team

---

## 目录

1. [部署指南](#1-部署指南)
2. [服务拓扑](#2-服务拓扑)
3. [扩缩容](#3-扩缩容)
4. [监控与告警](#4-监控与告警)
5. [日志管理](#5-日志管理)
6. [数据库运维](#6-数据库运维)
7. [故障排查 Checklist](#7-故障排查-checklist)
8. [常用命令速查](#8-常用命令速查)
9. [Control Plane Operations](#9-control-plane-operations)

---

## 1. 部署指南

### 1.1 Docker Compose 分层架构

Wisdoverse Cell 采用分层 Compose 文件组合，按职责隔离基础设施、应用、代理、可观测性：

```
docker/compose/
  docker-compose.base.yml          # 基础设施层: PostgreSQL, PgBouncer, Redis (主从+哨兵), NATS 3节点, Milvus
  docker-compose.app.yml           # 应用层: ai-core, gateway, web (含 Traefik labels)
  docker-compose.proxy.yml         # 代理层: Traefik v3.2 反向代理
  docker-compose.observability.yml # 可观测层: Prometheus, Grafana, Loki, Tempo, Promtail, Exporters
  docker-compose.override.yml      # 开发覆盖: 暴露调试端口, 单副本, 禁用 HA 组件
  docker-compose.prod.yml          # 生产覆盖: 预构建镜像, 多副本, 滚动更新策略
  docker-compose.loadtest.yml      # 负载测试: k6
```

层叠组合逻辑：

| 模式 | 组合文件 | 用途 |
|------|---------|------|
| 开发 | base + app + proxy + override | 单副本, debug 端口, 本地构建 |
| 生产 | base + app + proxy + observability + prod | 多副本, 预构建镜像, 可观测性全开 |
| 仅基础设施 | base + override | 本地代码开发连基础设施 |

### 1.2 开发环境

```bash
# 启动开发环境 (单副本, debug 端口暴露, 本地构建)
make up-dev

# 停止
make down-dev
```

开发环境特性：
- ai-core / gateway 各 1 副本
- `DEBUG=true`, `LOG_LEVEL=DEBUG`
- PostgreSQL 暴露 `5432`, Redis 暴露 `6379`, NATS 暴露 `4222/8222`, Milvus 暴露 `19530/9091`
- PgBouncer 暴露 `6432`
- HA 组件 (pg-replica, redis-replica, redis-sentinel) 默认禁用，启用需加 `--profile ha`

### 1.3 生产环境

```bash
# 启动生产环境 (多副本, 可观测性, 预构建镜像)
make up-prod

# 停止
make down-prod
```

生产环境特性：
- ai-core 默认 3 副本, gateway 默认 3 副本, web 默认 2 副本
- `DEBUG=false`, `LOG_LEVEL=INFO`, `LOG_FORMAT=json`
- 滚动更新: `parallelism=1`, `delay=10s`, `failure_action=rollback`
- 重启策略: `on-failure`, 最多 3 次, 延迟 5s
- 不暴露基础设施端口 (仅通过 Traefik 访问)

**必需环境变量** (写入 `.env` 文件):

```bash
POSTGRES_PASSWORD=<strong-password>
AUTH_SECRET=<nextauth-secret>
REGISTRY=registry.example.com/     # 生产镜像仓库前缀
VERSION=1.0.0                      # 镜像版本标签
ANTHROPIC_API_KEY=<your-anthropic-api-key>       # Claude API Key
FEISHU_APP_ID=cli_xxxx
FEISHU_APP_SECRET=xxxx
FEISHU_VERIFICATION_TOKEN=xxxx
FEISHU_ENCRYPT_KEY=xxxx
ALERTMANAGER_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
```

### 1.4 仅基础设施 (本地开发用)

```bash
# 仅启动 PostgreSQL, PgBouncer, Redis, NATS, Milvus (暴露调试端口)
make up-infra

# 停止
make down-infra
```

适用场景：开发者在本地直接运行 Python/Go 进程，只需要数据库和消息队列。

### 1.5 Control Plane Runtime Switches

The control-plane ledger is opt-in until migrations have been applied and the
operator API is ready for the target environment.

```bash
CONTROL_PLANE_ENABLED=true
CONTROL_PLANE_COMPANY_ID=cmp_projectcell
CONTROL_PLANE_APPROVAL_ENFORCED=true
CONTROL_PLANE_LLM_BUDGET_ENFORCED=true
CONTROL_PLANE_TOOL_BUDGET_ENFORCED=true
CONTROL_PLANE_LOCAL_ADAPTER_ENABLED=false
CONTROL_PLANE_LOCAL_ADAPTER_ALLOWLIST=
```

Keep `CONTROL_PLANE_LOCAL_ADAPTER_ENABLED=false` in production unless a reviewed
adapter allowlist is in place. The recommended production execution boundary for
frontend-created agents is the `http` adapter pointing at a deployed
`create_agent_app()` service and its authenticated `/agent/request` endpoint.

Tool budget enforcement applies to `ToolRegistry` entries that declare
`estimated_cost_usd`. Successful high-cost tool calls merge that estimate into
the current `AgentRun`; when `CONTROL_PLANE_TOOL_BUDGET_ENFORCED=true`, the
same call is checked by `BudgetGuard` before the handler runs.

---

## 2. 服务拓扑

### 2.1 基础设施层

| 服务 | 镜像 | 端口(内部) | 端口(开发暴露) | 健康检查 | 资源限制 |
|------|------|-----------|--------------|---------|---------|
| postgres | postgres:18-alpine | 5432 | 5432 | `pg_isready` / 10s | 1G (prod: 2G) |
| pg-replica | postgres:18-alpine | 5432 | - | `pg_isready` / 10s | 1G |
| pgbouncer | edoburu/pgbouncer:1.22.0 | 6432 | 6432 | `pg_isready :6432` / 10s | 128M |
| redis-master | redis:8-alpine | 6379 | 6379 | `redis-cli ping` / 10s | 384M (prod: 512M) |
| redis-replica-1 | redis:8-alpine | 6379 | - | `redis-cli ping` / 10s | 384M |
| redis-replica-2 | redis:8-alpine | 6379 | - | `redis-cli ping` / 10s | 384M |
| redis-sentinel-{1,2,3} | redis:8-alpine | 26379 | - | - | 64M |
| nats-{1,2,3} | nats:2.10-alpine | 4222/8222 | 4222/8222 (nats-1) | `wget :8222/healthz` / 10s | 512M |
| milvus | milvusdb/milvus:v2.6.10 | 19530/9091 | 19530/9091 | `curl :9091/healthz` / 15s | 2G |

### 2.2 应用层

| 服务 | 镜像 | 端口(内部) | 健康检查 | 副本数(dev/prod) | 资源限制(prod) |
|------|------|-----------|---------|-----------------|---------------|
| ai-core | projectcell/ai-core | 8000 (HTTP) / 50051 (gRPC) | `curl :8000/health` / 15s | 1 / 3 | 2 CPU, 2G |
| gateway | projectcell/gateway | 8080 | `wget :8080/health` / 15s | 1 / 3 | 1 CPU, 256M |
| web | projectcell/web | 3000 | `node fetch :3000` / 15s | 1 / 2 | 0.5 CPU, 256M |

### 2.3 代理层

| 服务 | 镜像 | 端口(外部) | 健康检查 | 资源限制 |
|------|------|-----------|---------|---------|
| traefik | traefik:v3.2 | 80 (HTTP), 50051 (gRPC), 8081 (Dashboard) | `traefik healthcheck --ping` / 10s | 1 CPU, 256M |

**Traefik 路由规则**:

| 路径前缀 | 目标服务 | 中间件 |
|----------|---------|--------|
| `/api`, `/health`, `/docs`, `/metrics` | ai-core:8000 | - |
| `/webhook` | gateway:8080 | ratelimit, circuit-breaker |
| `/grafana` | grafana:3000 | - |
| `/` (fallback, priority=1) | web:3000 | compress, security-headers |
| gRPC (`/`) on :50051 | ai-core:50051 (h2c) | - |

### 2.4 可观测性层

| 服务 | 镜像 | 端口(内部) | 健康检查 | 资源限制 |
|------|------|-----------|---------|---------|
| prometheus | prom/prometheus:v2.51.0 | 9090 | `wget :9090/-/healthy` | 1G |
| alertmanager | prom/alertmanager:v0.27.0 | 9093 | `wget :9093/-/healthy` | 128M |
| grafana | grafana/grafana:11.4.0 | 3000 | `wget :3000/api/health` | 512M |
| loki | grafana/loki:3.3.2 | 3100 | `wget :3100/ready` | 512M |
| tempo | grafana/tempo:2.6.1 | 3200 (HTTP) / 4317 (OTLP) | `wget :3200/ready` | 512M |
| promtail | grafana/promtail:3.3.2 | - | - | 128M |
| postgres-exporter | prometheuscommunity/postgres-exporter:v0.15.0 | 9187 | - | 64M |
| redis-exporter | oliver006/redis_exporter:v1.66.0 | 9121 | - | 64M |
| pgbouncer-exporter | prometheuscommunity/pgbouncer-exporter:v0.8.0 | 9127 | - | 64M |
| nats-exporter | natsio/prometheus-nats-exporter:0.15.0 | 7777 | - | 64M |

### 2.5 网络拓扑

```
                        Internet
                           |
                      [ Traefik :80 ]  ----  frontend network
                       /     |     \
                    web   ai-core  gateway    grafana
                           |         |
                    ----- backend network -----
                    |        |        |       |
                postgres   redis   nats    milvus
                pgbouncer  sentinel        prometheus
                pg-replica replica         loki/tempo
```

- **frontend**: Traefik + 应用服务 + Grafana
- **backend**: 所有基础设施 + 应用服务 + 可观测性组件

---

## 3. 扩缩容

### 3.1 水平扩缩命令

```bash
# 扩缩 ai-core (CPU 密集型, LLM 调用)
make scale-ai-core N=5

# 扩缩 gateway (I/O 密集型, webhook 处理)
make scale-gateway N=5

# 扩缩 web (前端)
make scale-web N=3
```

底层命令：

```bash
docker compose -f docker/compose/docker-compose.app.yml up -d --scale ai-core=5 --no-recreate
```

### 3.2 Traefik 自动服务发现

Traefik 通过 Docker socket 监听容器启停事件，自动将新副本加入负载均衡池。扩缩容后无需手动配置。

验证扩缩是否生效：

```bash
# 查看 Traefik Dashboard
open http://localhost:8081

# 或通过 API 查看后端服务器列表
curl -s http://localhost:8081/api/http/services | jq '.[] | select(.name | contains("ai-core"))'
```

### 3.3 资源限制参考表

| 服务 | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|------|-----------|-------------|--------------|-----------------|
| ai-core | 2 | 2G | 1 (prod) / 0.5 (dev) | 1G (prod) / 512M (dev) |
| gateway | 1 | 256M | 0.5 (prod) / 0.25 (dev) | 128M (prod) / 64M (dev) |
| web | 1 (dev) / 0.5 (prod) | 512M (dev) / 256M (prod) | 0.25 | 128M |
| postgres | - | 1G (dev) / 2G (prod) | - / 1 (prod) | 512M / 1G (prod) |
| redis-master | - | 384M (dev) / 512M (prod) | - | 128M / 256M (prod) |
| nats-{1,2,3} | - | 512M | - | 128M |
| milvus | - | 2G | - | 1G |
| traefik | 1 | 256M | 0.25 | 64M |

### 3.4 扩缩容决策指南

| 信号 | 动作 |
|------|------|
| ai-core P99 > 2s 且 CPU > 80% | `make scale-ai-core N=<current+2>` |
| gateway P99 > 500ms 且 连接数高 | `make scale-gateway N=<current+2>` |
| PostgreSQL 连接 > 80% max_connections | 检查 PgBouncer 配置, 或扩 ai-core 减少单实例连接 |
| Redis memory > 80% maxmemory | 清理过期 key, 或调整 maxmemory |

---

## 4. 监控与告警

### 4.1 告警规则总览

共 **51 条 Prometheus 告警规则**, 分布在 3 个规则文件中：

| 类别 | 文件 | 规则数 | 覆盖范围 |
|------|------|--------|---------|
| 基础设施 | `infrastructure.yml` | 23 | PostgreSQL, Redis, CPU/内存/磁盘, 容器重启/OOM |
| 应用 SLO | `application.yml` | 16 | P99 延迟, 5xx 错误率, Agent 健康, LLM API, Tool Call, EventBus |
| 业务指标 | `business.yml` | 12 | 飞书 Webhook, 同步管道, Card Callback, 日报推送, 任务分解 |

### 4.2 关键 SLO 指标

| 指标 | SLO 目标 | 告警阈值 (warning) | 告警阈值 (critical) |
|------|---------|-------------------|-------------------|
| HTTP P99 延迟 | < 2s | > 2s (5m) | > 5s (2m) |
| HTTP 5xx 错误率 | < 1% | > 1% (5m) | > 5% (2m) |
| LLM API 错误率 | < 5% | > 5% (5m) | > 10% (3m) |
| LLM 日预算 | < $100 | > $80 (5m) | > $100 (1m) |
| Card Callback P95 | < 12s | > 12s (5m) | > 14s (2m) |
| Event Queue 积压 | < 1000 | > 1000 (10m) | > 5000 (5m) |
| PostgreSQL 连接使用率 | < 80% | > 80% (5m) | > 90% (2m) |
| Redis 内存使用率 | < 80% | > 80% (5m) | > 95% (2m) |

### 4.3 AlertManager 路由

AlertManager 将告警通过 webhook 发送到飞书群：

| 严重级别 | group_wait | repeat_interval | 行为 |
|---------|-----------|-----------------|------|
| critical | 10s | 1h | 立即通知, 每小时重复 |
| warning | 30s | 4h | 30s 聚合, 每 4 小时重复 |
| info | 5m | 12h | 5 分钟聚合, 每 12 小时重复 |

**抑制规则**:
- critical 触发时, 抑制同名 warning
- AgentDown 触发时, 抑制该 job 的所有 warning/info 告警

**配置位置**: `docker/prometheus/alertmanager.yml`

**必需环境变量**:

```bash
ALERTMANAGER_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/<your-token>
```

### 4.4 Grafana Dashboard

```bash
# 访问 Grafana (通过 Traefik 代理)
open http://localhost/grafana

# 默认凭据
# 用户名: admin
# 密码: projectcell (通过 GRAFANA_ADMIN_PASSWORD 环境变量覆盖)
```

数据源 (已通过 provisioning 自动配置):
- **Prometheus**: 指标查询
- **Loki**: 日志查询
- **Tempo**: 分布式追踪

Dashboard 定义文件: `docker/grafana/dashboards/`
Provisioning 配置: `docker/grafana/provisioning/`

### 4.5 手动检查告警状态

```bash
# 查看 Prometheus 当前告警
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {alertname: .labels.alertname, state: .state, severity: .labels.severity}'

# 查看 AlertManager 活跃告警
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | {alertname: .labels.alertname, status: .status.state}'

# 重新加载 Prometheus 配置 (无需重启)
curl -X POST http://localhost:9090/-/reload
```

---

## 5. 日志管理

### 5.1 日志管道

```
容器 stdout/stderr
       |
   Docker json-file driver (50M x 5 files)
       |
   Promtail (读取 /var/lib/docker/containers)
       |
   Loki (3100) -- 存储 + 索引
       |
   Grafana (查询 + 可视化)
```

### 5.2 日志驱动配置

所有容器统一使用 `json-file` driver:

```yaml
logging:
  driver: json-file
  options:
    max-size: "50m"    # 单文件最大 50MB
    max-file: "5"      # 最多保留 5 个轮转文件
    labels: "service,environment"
```

可观测性组件自身使用更小的日志配额 (`25m x 3`)，避免磁盘占用过大。

### 5.3 结构化日志格式

应用层输出 JSON 结构化日志，包含以下关键字段：

```json
{
  "timestamp": "2026-03-07T10:30:00.123Z",
  "level": "INFO",
  "message": "Event processed",
  "trace_id": "tr_01HWZX...",
  "agent_name": "chat-agent",
  "event_type": "chat.message_received",
  "duration_ms": 145
}
```

生产环境强制 `LOG_FORMAT=json`; 开发环境可设置 `LOG_FORMAT=text` 以便阅读。

### 5.4 日志查看命令

```bash
# 查看全部服务日志 (base + app + proxy)
make logs

# 仅查看应用层日志 (ai-core, gateway, web)
make logs-app

# 查看可观测性组件日志
make logs-obs

# 查看单个服务日志
docker compose -f docker/compose/docker-compose.base.yml logs -f postgres
docker compose -f docker/compose/docker-compose.app.yml logs -f ai-core

# 按 trace_id 查询日志 (通过 Grafana Loki)
# Explore > Loki > LogQL:
# {job="ai-core"} |= "tr_01HWZX"

# 按 agent 过滤日志
# {job="ai-core"} | json | agent_name="chat-agent"
```

---

## 6. 数据库运维

### 6.1 初始化脚本

PostgreSQL 容器首次启动时按字母序执行 `docker/init-scripts/` 下的脚本：

| 脚本 | 作用 |
|------|------|
| `01-init.sql` | 启用 `uuid-ossp`, `pg_trgm` 扩展; 创建 `projectcell` schema |
| `02-agent-users.sql` | 创建 per-agent 数据库用户 (最小权限原则) |

**注意**: 这些脚本仅在 `postgres_data` volume 为空时执行。已有数据的环境需手动运行。

### 6.2 Per-Agent 数据库用户

| 用户 | 默认密码(dev) | 权限范围 |
|------|-------------|---------|
| `chat_agent` | `chat_agent_dev` | CRUD: `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress` |
| `pjm_agent` | `pjm_agent_dev` | CRUD: `pjm_agent_alert_logs`, `pjm_agent_config_cache`, `pjm_agent_decomposition_records` |
| `sync_agent` | `sync_agent_dev` | CRUD: `sync_agent_mappings`, `sync_agent_subtask_mappings`, `sync_agent_logs`, `sync_agent_locks` |
| `analysis_agent` | `analysis_agent_dev` | CRUD: `analysis_agent_report_logs`; SELECT: 其他 agent 的表 (用于跨 agent 分析) |

所有 agent 用户均有 `CONNECT`, `USAGE ON SCHEMA public`, `USAGE ON ALL SEQUENCES` 权限。

**生产环境必须替换默认密码。**

### 6.3 手动重新授权

若表由 Alembic/SQLAlchemy 后创建, 需重新运行授权脚本:

```bash
docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  psql -U projectcell -d projectcell -f /docker-entrypoint-initdb.d/02-agent-users.sql
```

### 6.4 备份与恢复

**备份** (推荐在生产环境配置定时备份容器):

```bash
# 手动全量备份 (custom format, 支持并行恢复)
docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  pg_dump -U projectcell -d projectcell -Fc --no-owner \
  > backup_$(date +%Y%m%d_%H%M%S).dump

# 验证备份完整性
pg_restore --list backup_20260307_100000.dump | head -20
```

**定时备份方案** (docker-compose 侧挂容器):

```yaml
# 可添加到 docker-compose.base.yml 或单独的 backup compose 文件
pg-backup:
  image: postgres:18-alpine
  entrypoint: /bin/sh
  command:
    - -c
    - |
      while true; do
        PGPASSWORD=$${POSTGRES_PASSWORD} pg_dump \
          -h postgres -U $${POSTGRES_USER} -d $${POSTGRES_DB} -Fc \
          > /backups/projectcell_$$(date +%Y%m%d_%H%M%S).dump
        # 保留 7 天
        find /backups -name "*.dump" -mtime +7 -delete
        sleep 86400  # 24 小时
      done
  volumes:
    - pg_backups:/backups
  depends_on:
    postgres:
      condition: service_healthy
```

**恢复**:

```bash
# 恢复全量备份到现有数据库 (会覆盖)
docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  pg_restore -U projectcell -d projectcell --clean --if-exists --no-owner \
  < backup_20260307_100000.dump

# 恢复到新数据库
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  createdb -U projectcell projectcell_restored

docker compose -f docker/compose/docker-compose.base.yml exec -T postgres \
  pg_restore -U projectcell -d projectcell_restored --no-owner \
  < backup_20260307_100000.dump
```

### 6.5 读写分离

生产环境启用 pg-replica 实现流复制：

```bash
# 查看复制状态
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "SELECT client_addr, state, sent_lsn, replay_lsn, replay_lag FROM pg_stat_replication;"

# 查看 replica 延迟
docker compose -f docker/compose/docker-compose.base.yml exec pg-replica \
  psql -U projectcell -c "SELECT now() - pg_last_xact_replay_timestamp() AS replication_delay;"
```

应用层通过环境变量 `DB_READ_HOST` / `DB_READ_PORT` 配置读副本连接。

---

## 7. 故障排查 Checklist

### 7.1 服务不可用

```bash
# Step 1: 检查健康状态
curl -f http://localhost/health          # ai-core (via Traefik)
curl -f http://localhost:8081/ping       # Traefik 自身

# Step 2: 查看容器状态
make ps
docker compose -f docker/compose/docker-compose.base.yml \
               -f docker/compose/docker-compose.app.yml ps

# Step 3: 查看故障容器日志
docker compose -f docker/compose/docker-compose.app.yml logs --tail=100 ai-core

# Step 4: 检查资源使用
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Step 5: 重启故障服务
docker compose -f docker/compose/docker-compose.app.yml restart ai-core

# Step 6: 如果依赖服务也有问题, 重启整个栈
make restart
```

### 7.2 高延迟

```bash
# Step 1: 检查 P99 延迟
curl -s http://localhost:9090/api/v1/query?query=job:http_request_duration_seconds:p99_5m | jq '.data.result'

# Step 2: 检查数据库慢查询
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
    FROM pg_stat_activity
    WHERE state != 'idle'
    ORDER BY duration DESC
    LIMIT 10;
  "

# Step 3: 检查 PgBouncer 连接池状态
docker compose -f docker/compose/docker-compose.base.yml exec pgbouncer \
  psql -p 6432 -U projectcell pgbouncer -c "SHOW POOLS;"

# Step 4: 检查 Redis 延迟
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli --latency-history -i 1

# Step 5: 扩容
make scale-ai-core N=5
```

### 7.3 PostgreSQL 连接耗尽

```bash
# Step 1: 查看当前连接分布
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT usename, client_addr, state, count(*)
    FROM pg_stat_activity
    GROUP BY usename, client_addr, state
    ORDER BY count DESC;
  "

# Step 2: 查看 max_connections 使用率
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT count(*) AS current,
           setting::int AS max,
           round(count(*)::numeric / setting::numeric * 100, 1) AS pct
    FROM pg_stat_activity, pg_settings
    WHERE pg_settings.name = 'max_connections'
    GROUP BY setting;
  "

# Step 3: 终止 idle 连接 (谨慎操作)
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE state = 'idle'
      AND query_start < now() - interval '10 minutes'
      AND usename != 'projectcell';
  "

# Step 4: 检查 PgBouncer 配置是否合理
docker compose -f docker/compose/docker-compose.base.yml exec pgbouncer \
  psql -p 6432 -U projectcell pgbouncer -c "SHOW CONFIG;" | grep -E "pool_size|max_client"
```

### 7.4 Redis 内存高

```bash
# Step 1: 查看内存使用
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation"

# Step 2: 查找大 key
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli --bigkeys

# Step 3: 按前缀统计 key 数量
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli --scan --pattern "event:*" | wc -l

# Step 4: 清理过期数据 (如果 eviction policy 是 noeviction)
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli DBSIZE

# Step 5: 手动清理特定前缀 (谨慎)
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  sh -c 'redis-cli --scan --pattern "temp:*" | xargs -L 100 redis-cli DEL'
```

### 7.5 LLM API 失败

```bash
# Step 1: 检查 LLM 错误率
curl -s 'http://localhost:9090/api/v1/query?query=job:llm_error_rate:ratio_5m' | jq '.data.result'

# Step 2: 查看 ai-core 日志中的 LLM 相关错误
docker compose -f docker/compose/docker-compose.app.yml logs --tail=200 ai-core | grep -i "anthropic\|claude\|llm\|api_error"

# Step 3: 检查 API Key 是否有效 (不要在日志中暴露完整 key)
docker compose -f docker/compose/docker-compose.app.yml exec ai-core \
  python -c "import os; k=os.environ.get('ANTHROPIC_API_KEY',''); print(f'Key present: {bool(k)}, prefix: {k[:12]}...')"

# Step 4: 检查 LLM 日预算消耗
curl -s 'http://localhost:9090/api/v1/query?query=llm_daily_cost_dollars' | jq '.data.result[0].value[1]'

# Step 5: 检查 Circuit Breaker 状态
docker compose -f docker/compose/docker-compose.app.yml logs --tail=50 ai-core | grep -i "circuit"

# Step 6: 检查 Anthropic API 状态页
# https://status.anthropic.com
```

### 7.6 NATS/EventBus 问题

```bash
# Step 1: 检查 NATS 集群状态
curl -s http://localhost:8222/varz | jq '{server_id, cluster: .cluster, jetstream: .jetstream}'

# Step 2: 检查 JetStream 流状态
curl -s http://localhost:8222/jsz | jq '.streams'

# Step 3: 查看 Event Queue 积压
curl -s 'http://localhost:9090/api/v1/query?query=event_queue_length' | jq '.data.result'

# Step 4: 查看事件处理错误
curl -s 'http://localhost:9090/api/v1/query?query=increase(event_processing_errors_total[1h])' | jq '.data.result'
```

---

## 8. 常用命令速查

### 8.1 启停管理

```bash
make up-dev          # 启动开发环境
make up-prod         # 启动生产环境
make up-infra        # 仅启动基础设施
make down-dev        # 停止开发环境
make down-prod       # 停止生产环境
make down-infra      # 停止基础设施
make restart         # 重启全部服务
make monitoring-up   # 启动可观测性栈
make monitoring-down # 停止可观测性栈
```

### 8.2 日志查看

```bash
make logs            # 全部服务日志 (follow)
make logs-app        # 仅应用层日志 (follow)
make logs-obs        # 可观测性组件日志 (follow)
make ps              # 查看运行中容器
```

### 8.3 扩缩容

```bash
make scale-ai-core N=5    # ai-core 扩到 5 副本
make scale-gateway N=5    # gateway 扩到 5 副本
make scale-web N=3        # web 扩到 3 副本
```

### 8.4 构建

```bash
make build               # 构建应用层 Docker 镜像
make build-no-cache      # 无缓存构建
```

### 8.5 测试

```bash
make test                # 运行全部测试
make test-unit           # 仅单元测试
make test-integration    # 仅集成测试
make docker-test         # Docker 环境测试
make load-smoke          # k6 冒烟测试 (10 VUs, 1 min)
make load-test           # k6 负载测试 (100 VUs, 8 min)
make load-stress         # k6 压力测试 (up to 500 VUs, 13 min)
make load-spike          # k6 峰值测试 (10->500->10 VUs)
```

### 8.6 清理

```bash
make clean               # 删除所有容器、volumes, 系统清理
```

### 8.7 数据库操作

```bash
# 连接主库
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -d projectcell

# 连接 PgBouncer
docker compose -f docker/compose/docker-compose.base.yml exec pgbouncer \
  psql -p 6432 -U projectcell projectcell

# 连接 Redis
docker compose -f docker/compose/docker-compose.base.yml exec redis-master \
  redis-cli

# 查看数据库大小
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -c "SELECT pg_size_pretty(pg_database_size('projectcell'));"

# 查看各表大小
docker compose -f docker/compose/docker-compose.base.yml exec postgres \
  psql -U projectcell -d projectcell -c "
    SELECT schemaname, tablename,
           pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
    FROM pg_tables
    WHERE schemaname NOT IN ('pg_catalog','information_schema')
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
    LIMIT 20;
  "
```

### 8.8 Proto 生成

```bash
make proto               # 生成全部 protobuf 代码 (Python + Go)
make proto-python        # 仅 Python gRPC
make proto-go            # 仅 Go gRPC (gateway)
```

---

## 9. Control Plane Operations

Related contract docs:

- [SPEC](../../SPEC.md) defines the control-plane goal and service boundaries.
- [API Reference: Control Plane API](./api-reference.md#control-plane-api) documents operator endpoints and request shapes.
- [Event Catalog: Control Plane Domain](./event-catalog.md#30-control-plane-domain) documents emitted evidence events.

### 9.1 Apply Ledger Migrations

The control-plane API depends on the shared ledger tables. Apply migrations
before enabling `CONTROL_PLANE_ENABLED=true`.

```bash
alembic upgrade head
alembic heads
```

The expected head includes `20260501_control_plane_ledger`.

### 9.2 Verify Agent Request Boundary

Every deployed agent created with `create_agent_app()` exposes an internal
request boundary:

```bash
curl -X POST \
  -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8012/agent/request \
  -d '{"action":"wakeup","input":{"task":"ping"}}'
```

Use this boundary for control-plane `http` adapter definitions. Do not route
frontend-created agents through direct imports of another agent service.

### 9.3 Wake A Frontend-Created Agent

```bash
curl -X POST \
  -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/control-plane/agents/ops-runner/wake \
  -d '{"actor_id":"human:operator","trace_id":"trace_manual","input":{}}'
```

Then inspect evidence:

```bash
curl -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  "http://localhost:8000/api/v1/control-plane/runs?agent_id=ops-runner"

curl -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  "http://localhost:8000/api/v1/control-plane/timeline?trace_id=trace_manual"
```

### 9.4 Run Heartbeat Scheduler Tick

Opt an active agent into scheduler execution through its adapter config:

```json
{
  "heartbeat_enabled": true,
  "heartbeat_interval_seconds": 300
}
```

Run one due-heartbeat pass from a trusted production scheduler:

```bash
curl -X POST \
  -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/control-plane/scheduler/heartbeats/run-once \
  -d '{"company_id":"cmp_default","limit":500}'
```

Each due heartbeat creates a normal `AgentRun` with a generated trace, an
`agent.wakeup-requested` input event, an `agent.wakeup-completed` output event,
and `agent_run.*` audit records whose trigger is `scheduled_heartbeat`.

### 9.5 Local Adapter Safety

`process`, `codex_local`, and `claude_local` adapters execute an explicit
operator-configured command. They fail closed unless:

```bash
CONTROL_PLANE_LOCAL_ADAPTER_ENABLED=true
CONTROL_PLANE_LOCAL_ADAPTER_ALLOWLIST=process:ops-runner,codex_local:dev-agent
```

Production deployments should prefer the `http` adapter. Enable local adapters
only in controlled environments with reviewed commands, isolated working
directories, and audited run output. Allowlist entries are exact by default:
`{adapter_type}:{agent_id}`. An agent may set `adapter_config.allowlist_key`
when a more specific registry key is required.

---

> **文档维护**: 本文档应随基础设施变更同步更新。任何 Compose 文件或告警规则的修改，请同步更新对应章节。
