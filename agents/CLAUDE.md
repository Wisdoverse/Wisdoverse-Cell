# Agent Development Standards

This directory contains all Wisdoverse Cell agents. Each agent is an independent microservice.

## Agent Structure

Every agent MUST follow this layout:

```
agents/<agent_name>/
  app/main.py          # FastAPI entry via create_agent_app()
  service/agent.py     # BaseAgent subclass
  core/                # Business logic
  models/              # Pydantic v2 models
  db/                  # Repository pattern (if needed)
  api/                 # API routes/schemas
  tests/
    unit/              # Unit tests (mocked deps)
    integration/       # Integration tests (real DB/Redis)
  Dockerfile
  requirements.txt
```

## Required Patterns

- **Entry point**: Use `create_agent_app()` from `shared/app/`, not manual lifespan/middleware
- **Agent class**: Inherit `BaseAgent`, implement `handle_event()`, `startup()`, `shutdown()`
- **Agent ID**: kebab-case (`requirement-manager`, not `requirement_manager`)
- **Events**: `Event(event_id="evt_{ulid}", event_type="{domain}.{action}", ...)`
- **Scheduler jobs**: Call `runtime.agent` (wrapped), not `_raw_agent`
- **Plugins**: Extend via `runtime.use(MyPlugin())`, not by modifying runtime
- **Models**: Pydantic v2 — `model_config = ConfigDict()`, `model_dump_json()`
- **Async**: All I/O must be async. Never block the event loop.
- **Imports**: Canonical paths only (`shared.integrations.*`, `shared.messaging.*`, `shared.infra.*`)

## Multi-Turn Conversations

Agents with multi-turn tool-calling loops should use `ConversationEngine` from `shared/infra/conversation_engine.py`:
- Creates per-request (not singleton) — pass loaded history as `messages=`
- Handles compression (MicroCompact + L1/L2), error recovery (ReactiveCompact), and tool execution
- `async for event in engine.run(message)` — yields typed events
- `chat_agent` is the reference consumer

## System Prompts

Follow Claude Code system prompt pattern:
- Tool definitions passed via API `tools` param — prompts teach usage STRATEGY, not tool lists
- Sections: System → Doing Tasks → Executing Actions → Output Efficiency
- Include anti-patterns ("不要...")
- chat_agent = 前台 (receptionist), Coordinator = CEO. Don't give agents responsibilities above their role.

## Testing

```bash
python -m pytest agents/<agent_name>/tests/ -v    # Run agent tests
ruff check agents/<agent_name>/                    # Lint
```

## Docker

```bash
docker build -f agents/<agent_name>/Dockerfile -t <agent_name> .
docker compose up <agent_name>                    # Via docker-compose.yml
```

## Current Agents

| Agent | Role | Purpose |
|-------|------|---------|
| chat_agent | 前台 | 用户直接对话，简单查询直接回，复杂指令升级给 Coordinator |
| coordinator | CEO | 全局编排引擎，跨 Agent 决策（见 coordinator-agent-design.md） |
| requirement_manager | PM | 需求提取/确认/PRD 生成 |
| pjm_agent | PMO | 任务拆解/审批/预警/报表 |
| sync_agent | PMO | OP ↔ 飞书双向同步 |
| analysis_agent | PMO | 风险检测/数据分析 |
| dev_agent | 执行 | 自动化开发 Agent (AgentForge) |
| qa_agent | 执行 | QA 验收 Agent |
| evolution_agent | 观察 | 自进化引擎 (L1/L2/L3)，全局优化 |
| channel_gateway | 基础设施 | 多渠道消息网关 |
