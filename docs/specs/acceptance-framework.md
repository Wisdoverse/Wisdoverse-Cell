# AI-Native Acceptance Framework

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **Status**: Draft | **Author**: Human + Claude | **Date**: 2026-03-20

## Problem Statement

Wisdoverse Cell 正在从 6 个 agent 扩展到 26 个。剩余 20 个 agent 将大量依赖 AI 工具（Claude Code、Codex、Gemini CLI）来实现。AI 生成的代码有一套独特的失败模式——幻觉式 import、自考自答的测试、spec 漂移、绕过 shared/ 重复造轮子——这些问题在人工 code review 中极易遗漏。

目前没有自动化的准入标准来阻止不合格代码进入主分支。一旦 AI 团队开始并行开发多个 agent，质量风险会指数级放大。

**不解决的代价**：低质量代码进入 main，架构退化，技术债积累速度超过 2 人团队的修复能力。

## Goals

1. **零安全/架构违规进入 main** — L0 GATE 自动阻断，无需人工介入
2. **AI 特有的失败模式有专项检测** — 幻觉 import、自考自答测试、spec 漂移至少 3 项可自动检测
3. **新 agent 上线有明确准入标准** — 可机器执行的 checklist，不依赖审查者的经验
4. **人类精力聚焦在需要判断力的决策上** — 客观检查自动化，只有主观判断才到人手里
5. **验收数据可追踪** — 每次验收结果留存，支持持续改进

## Non-Goals

- **不替代单元测试** — 本框架验收的是"代码是否达标"，不负责写测试本身
- **不做运行时监控** — Prometheus + Grafana 已覆盖，本框架只管代码准入阶段
- **不做 AI 模型选择/调优** — 不管是 Claude 还是 Gemini 写的，标准统一
- **不做部署门控** — 部署流程由现有 CI/CD 的 deploy stage 负责
- **V1 不做自动修复** — 只报告和阻断，不自动改代码（P2 考虑）

## User Stories

### 作为开发者（人类或 AI 工具）

- 作为开发者，我想在提交 MR 时自动获得验收结果，以便在 review 之前就知道哪些问题必须修复
- 作为开发者，我想看到清晰的 L0/L1/L2 分级，以便优先处理硬阻断问题而不是浪费时间在风格建议上
- 作为开发者（AI 工具），我想收到机器可解析的验收报告（JSON），以便自动根据反馈修复代码

### 作为项目负责人（2 人团队）

- 作为负责人，我想让安全和架构违规自动阻断 merge，以便不需要逐行 review 就能保证底线
- 作为负责人，我想只在 L1 CHECK 时被通知做决策，以便把精力花在真正需要判断的地方
- 作为负责人，我想看到每个新 agent 的验收报告汇总，以便了解 AI 团队的产出质量趋势

## Requirements

### Must-Have (P0)

#### P0-1: L0 GATE — 硬阻断检查

在 GitLab CI pipeline 的 `test` stage 之后、`build` stage 之前新增 `acceptance` stage，包含以下检查：

**安全检查：**
- [ ] 无硬编码密钥（API key、password、token 等），使用 pattern 匹配 + 熵检测
- [ ] 无 SQL 注入风险（raw SQL 拼接检测）
- [ ] 所有外部输入边界有 Pydantic 校验
- [ ] 不在日志中输出 PII 数据（检测 `logger.*` 调用中的敏感字段）

**架构检查：**
- [ ] 新 agent 必须继承 `BaseAgent`，使用 `create_agent_app()` 工厂函数
- [ ] 不得从 `shared.services.*` 导入（已废弃路径，见 CLAUDE.md）
- [ ] 不得在 agent 内部重新实现 `shared/` 已有功能（AST 相似度检测）
- [ ] Event 必须使用标准格式：`Event(event_id="evt_{ulid}", event_type="{domain}.{action}", ...)`
- [ ] 新 EventBus 事件类型必须在 `shared/schemas/` 中注册

**基础质量：**
- [ ] `ruff check` 零 error（warning 允许）
- [ ] 所有 import 可解析（无幻觉 import）— 静态分析验证每个 import 路径存在
- [ ] 类型标注覆盖所有公共函数签名
- [ ] 测试存在且覆盖率达到分类阈值（pytest-cov）：
  - **逻辑密集型 agent**（sync_agent, analysis_agent）：≥ 70%
  - **LLM 交互密集型 agent**（chat_agent, requirement_manager）：≥ 45%（LLM 调用路径难以 mock）
  - **混合型 agent**（pjm_agent, evolution_agent）：≥ 60%
  - 分类定义在 `.acceptance/config.yaml` 中，可按 agent 调整

**合规：**
- [ ] 含用户数据处理的 agent 必须实现 DSAR 接口（`shared/schemas/dsar.py`）

**验收结果**：任一项不通过 → MR pipeline 标记为 failed，阻断 merge。

#### P0-2: L1 CHECK — 软阻断检查

以下检查不通过时，在 MR 中自动添加 comment 并 @ 负责人，不自动阻断：

- [ ] **Spec 漂移检测**：比对 `docs/specs/` 中对应 spec 与实际实现的匹配度（LLM 判断）。检测是否实现了 spec 未要求的功能，或遗漏了 spec 要求的功能
- [ ] **测试质量**：覆盖率 60-80%（通过但不优秀）、断言密度低于阈值、缺少异常路径测试
- [ ] **自考自答检测**：当测试和实现由同一次 AI 会话生成时，检测测试是否只覆盖 happy path（断言密度分析 + 异常路径覆盖率）
- [ ] **过度工程**：引入了 spec 未要求的新抽象层、新依赖包、或新配置项
- [ ] **EventBus 一致性**：新事件类型在 `shared/schemas/` 注册但未被任何 consumer 订阅（死事件）
- [ ] **性能基准**：agent 启动时间 > 5s 或单次 `handle_event()` 平均耗时 > 2s（需基准数据）

**验收结果**：生成结构化报告，以 MR comment 形式展示，人类决定放行或打回。

#### P0-3: L2 REPORT — 仅报告

不影响 merge，结果保存到 artifact：

- [ ] 代码复杂度指标（圈复杂度 > 10 的函数列表）
- [ ] 注释/代码比（标记 AI 典型的过度注释：比率 > 0.4）
- [ ] 函数长度分布（> 50 行的函数列表）
- [ ] 依赖关系图变更（新增的 cross-agent 依赖）
- [ ] 文档完整性（README、docstring 覆盖率）

**验收结果**：JSON + Markdown 报告，存储为 CI artifact，供趋势分析。

#### P0-4: 新 Agent 上线专用 Checklist

除 L0-L2 通用检查外，新 agent 首次 merge 需额外通过：

- [ ] 继承 `BaseAgent`，实现 `handle_event()`、`startup()`、`shutdown()`
- [ ] 使用 `create_agent_app()` 创建 FastAPI 入口
- [ ] 独立 `Dockerfile` + Docker Compose service 定义
- [ ] 数据库隔离（独立 PostgreSQL database + Redis namespace）
- [ ] Prometheus metrics endpoint (`/metrics`)
- [ ] 健康检查 endpoint (`/health`)
- [ ] 至少 1 个 integration test 验证 EventBus 收发
- [ ] `docs/specs/` 中有对应 spec 文档
- [ ] 在 `CLAUDE.md` 的架构图中注册

#### P0-5: 验收报告格式

所有检查产出统一 JSON 格式，便于 AI 工具消费：

```json
{
  "framework_version": "1.0",
  "mr_id": "!123",
  "timestamp": "2026-03-20T12:00:00Z",
  "target": "agents/new_agent",
  "summary": {
    "l0_gate": "PASS",
    "l1_check": "WARN",
    "l2_report": "INFO"
  },
  "results": [
    {
      "level": "L0",
      "category": "security",
      "check": "no_hardcoded_secrets",
      "status": "PASS",
      "details": null
    },
    {
      "level": "L1",
      "category": "semantic",
      "check": "spec_drift",
      "status": "WARN",
      "details": "实现了 spec 未要求的 /admin endpoint",
      "spec_ref": "docs/specs/new-agent.md",
      "file": "agents/new_agent/routes.py",
      "line": 45
    }
  ]
}
```

### Nice-to-Have (P1)

#### P1-1: 验收趋势 Dashboard

- Grafana dashboard 展示过去 30 天的验收通过率、按 level 和 category 分组
- 跟踪 AI 工具 vs 人类提交的通过率差异
- 标记反复出现的 L1 问题（可能需要升级为 L0）

#### P1-2: 验收反馈自动回传 AI 工具

- L0 不通过时，自动生成修复指令（machine-readable），回传给 Claude Code / Codex
- 支持 AI 工具读取验收报告后自动修复并重新提交

#### P1-3: Go Gateway 验收规则

- 扩展框架覆盖 `gateway/` Go 代码（golangci-lint、Go 安全扫描、gRPC contract 检查）

#### P1-4: Next.js Frontend 验收规则

- 扩展框架覆盖 `frontend/`（TypeScript strict、a11y 检查、bundle size 阈值）

### Future Considerations (P2)

#### P2-1: QA Agent

- 将验收框架封装为 Wisdoverse Cell 的第 7 个 agent（`qa_agent`）
- 能被 PJM Agent 调度，在任务流中自动触发验收
- 具备 L3 自进化能力——根据历史验收数据自动调整阈值

#### P2-2: 自动修复

- L0 不通过时自动调用 AI 工具修复并重新提交
- 需要防止无限循环（最多重试 2 次，之后升级到人类）

#### P2-3: Cross-Agent 集成验收

- 验证新 agent 与现有 agent 的 EventBus 交互是否正确
- 端到端流程测试（从消息输入到跨 agent 协作到输出）

## Success Metrics

### Leading Indicators（上线后 1-2 周）

| 指标 | 目标 | 测量方法 |
|------|------|----------|
| L0 检查自动阻断率 | 100% 的 L0 违规被阻断 | CI pipeline 日志 |
| 误报率 | L0 < 5%，L1 < 20% | 人工标记误报 / 总报告数 |
| Pipeline 增加耗时 | < 2 分钟 | CI pipeline duration diff |
| AI 工具首次提交通过率 | > 40%（基线，用于跟踪改进） | 验收报告统计 |

### Lagging Indicators（上线后 1-3 月）

| 指标 | 目标 | 测量方法 |
|------|------|----------|
| 主分支安全/架构违规 | 归零 | 季度安全审计 |
| 新 agent 交付速度 | 从当前 ~2 周/agent 提升到 < 1 周/agent | 首次 MR 到 merge 时间 |
| 人工 review 时间 | 减少 50% | 负责人自评 |
| L1 问题趋势 | 同类问题月环比下降 | 验收报告趋势 |

## Open Questions

| # | 问题 | 负责人 | 阻断性 |
|---|------|--------|--------|
| 1 | Spec 漂移的 LLM 检测用哪个模型？Haiku 够用还是需要 Sonnet？ | Engineering | 非阻断（先用 Sonnet，后续降级验证） |
| 2 | AST 相似度检测 shared/ 重复实现的阈值定多少？ | Engineering | 非阻断（先保守设 80%，根据误报调整） |
| 3 | ~~测试覆盖率 60% 门槛~~ **已解决**：按 agent 类型分类——逻辑密集型 ≥ 70%、LLM 密集型 ≥ 45%、混合型 ≥ 60% | — | — |
| 4 | L1 的 MR comment 用 GitLab API 还是 webhook 推送到飞书？ | Engineering | 非阻断 |
| 5 | ~~验收框架代码位置~~ **已解决**：放 `.acceptance/`（项目根目录），属 pipeline 工具而非 agent 业务代码 | — | — |

## Timeline Considerations

**Phase 1（1 周）**：L0 GATE 上线
- 安全检查 + 架构检查 + 幻觉 import 检测
- 集成到 GitLab CI `acceptance` stage
- 用 `pjm_agent` 的 MR 验证误报率（pjm_agent 是混合型，覆盖逻辑+LLM 路径，代表性好）

**Phase 2（1 周）**：L1 CHECK + L2 REPORT 上线
- Spec 漂移 LLM 检测
- 自考自答测试检测
- JSON 报告生成 + MR comment 自动发布

**Phase 3（持续）**：用第一个新 agent 的开发来验证和调优
- 新 agent checklist 实战验证
- 根据实际误报率调整阈值
- 收集数据为 P1 趋势 Dashboard 做准备

**硬依赖**：
- GitLab CI runner 需支持在 `acceptance` stage 运行 Python 脚本
- L1 Spec 漂移检测依赖 Claude API（已有 LLM Gateway）
