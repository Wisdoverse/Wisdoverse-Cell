# 飞书深度集成产品需求文档 (PRD)

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **版本**: v1.0
> **创建日期**: 2026-01-23
> **状态**: Phase 1-2 已完成，Phase 3 待开发
> **产品负责人**: Claude
> **文档类型**: PRD / 产品规格说明
> **适用于**: [Ralph-Claude-Code](https://github.com/frankbria/ralph-claude-code) 自动化开发

---

## 1. 产品概述

### 1.1 产品背景

**Wisdoverse Cell** 是 AI Native OS，核心是 2 人 + 26 个 AI Agent 协作的智能公司。**需求管理 Agent (Requirement Manager)** 负责从会议记录中提取、追踪、管理客户需求。

当前痛点：
- 会议记录手动整理，耗时且易遗漏
- 需求确认流程割裂，需要切换多个系统
- 没有实时通知机制，响应延迟

### 1.2 产品目标

实现企业级飞书深度集成，让需求管理完全在飞书中闭环：

| 目标 | 描述 | 成功指标 |
|------|------|----------|
| **自动化提取** | 会议结束自动提取需求 | 提取延迟 < 30秒 |
| **即时反馈** | 在飞书卡片中确认/拒绝 | 24h 确认率 > 80% |
| **零切换** | 全流程不离开飞书 | 用户满意度 > 4.0/5.0 |

### 1.3 目标用户

| 角色 | 使用场景 | 核心诉求 |
|------|----------|----------|
| 产品经理 | 会议后确认需求 | 快速、准确、可追溯 |
| 研发负责人 | 评审需求优先级 | 清晰、可操作 |
| 客户成功 | 录入客户反馈 | 简单、直接 |

---

## 2. 功能清单

### 2.1 功能矩阵

| 功能 | Phase 1 | Phase 2 | Phase 3 | 优先级 |
|------|:-------:|:-------:|:-------:|:------:|
| Token 自动管理 | ✅ | - | - | P0 |
| 签名验证 | ✅ | - | - | P0 |
| 统一 Webhook | ✅ | - | - | P0 |
| 会议结束事件 | - | ✅ | - | P0 |
| Bot 消息处理 | - | ✅ | - | P0 |
| 交互式卡片 | - | ✅ | - | P0 |
| 卡片确认/拒绝 | - | ✅ | - | P0 |
| 日历事件订阅 | - | - | ⏳ | P1 |
| PRD 导出文档 | - | - | ⏳ | P1 |
| /list 命令 | - | - | ⏳ | P2 |
| /export 命令 | - | - | ⏳ | P2 |
| 批量操作 | - | - | ⏳ | P2 |

### 2.2 功能完成状态

```
Phase 1 (基础设施)    ████████████████████ 100%
Phase 2 (核心功能)    ████████████████████ 100%
Phase 3 (增强功能)    ░░░░░░░░░░░░░░░░░░░░   0%
```

---

## 3. 用户故事

### US-001: 会议自动提取 [已完成]

**用户故事**:
> 作为产品经理，我希望会议结束后自动提取需求并发送到群里，这样我不用手动整理会议纪要。

**验收标准**:
- [x] 会议结束事件触发提取流程
- [x] 需求以卡片形式发送到会议群
- [x] 卡片显示需求标题、描述、优先级
- [x] 卡片包含"确认"和"拒绝"按钮
- [x] 处理延迟 < 30 秒

**流程图**:
```
会议结束 → 飞书推送事件 → EventHandler 处理 → Agent 提取需求 → 发送卡片
```

---

### US-002: Bot 交互提取 [已完成]

**用户故事**:
> 作为团队成员，我希望 @机器人 发送会议记录就能提取需求，这样我可以随时处理任何文本。

**验收标准**:
- [x] Bot 响应群内 @提及
- [x] 文本内容被处理提取
- [x] 结果以卡片形式返回
- [x] /help 命令显示使用说明
- [x] 异常时返回友好错误信息

**支持的命令**:
| 命令 | 功能 | 状态 |
|------|------|------|
| (直接发文本) | 提取需求 | ✅ |
| /help | 显示帮助 | ✅ |
| /list | 查看待确认需求 | ⏳ Phase 3 |
| /export | 导出 PRD | ⏳ Phase 3 |

---

### US-003: 卡片确认/拒绝 [已完成]

**用户故事**:
> 作为产品负责人，我希望直接在卡片中确认或拒绝需求，这样我不用切换到其他系统。

**验收标准**:
- [x] 点击"确认"更新需求状态
- [x] 点击"拒绝"可输入原因
- [x] 操作后卡片更新显示结果
- [x] 记录操作人和时间
- [x] 操作结果 Toast 提示

**卡片状态流转**:
```
[待处理卡片] --点击确认--> [已确认卡片]
     |
     +--------点击拒绝--> [已拒绝卡片]
```

---

### US-004: 日历事件订阅 [Phase 3]

**用户故事**:
> 作为产品经理，我希望日历中标题含"需求"的会议自动被系统关注，这样我不会错过重要讨论。

**验收标准**:
- [ ] 订阅日历变更事件
- [ ] 过滤关键词: 需求, 产品, review, PRD
- [ ] 会议前发送提醒卡片
- [ ] 会议后自动提取（与 US-001 联动）

---

### US-005: PRD 导出到飞书文档 [Phase 3]

**用户故事**:
> 作为产品经理，我希望一键将已确认需求导出为飞书文档，这样我可以方便分享给团队。

**验收标准**:
- [ ] /export 命令触发导出
- [ ] 在飞书文档创建 PRD
- [ ] 文档包含所有已确认需求
- [ ] 返回可分享的文档链接

---

### US-006: 批量操作 [Phase 3]

**用户故事**:
> 作为产品负责人，我希望一次确认多个需求，这样我可以高效处理积压。

**验收标准**:
- [ ] /list 命令显示待确认列表
- [ ] 支持多选操作
- [ ] 批量确认
- [ ] 批量拒绝（共享原因）

---

## 4. 技术架构

### 4.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        飞书开放平台                              │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│   │ Bot Msg │  │ Cards   │  │ Events  │  │Calendar │          │
│   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘          │
└────────┼────────────┼────────────┼────────────┼────────────────┘
         │            │            │            │
         └────────────┴─────┬──────┴────────────┘
                            │
                            ▼
          ┌─────────────────────────────────────┐
          │      Unified Webhook Router         │
          │       POST /api/feishu/webhook      │
          └─────────────────┬───────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   ┌────────────┐   ┌────────────┐   ┌────────────┐
   │ BotHandler │   │CardHandler │   │EventHandler│
   │  文本提取  │   │  确认拒绝  │   │  会议事件  │
   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
                          ▼
          ┌─────────────────────────────────────┐
          │     Requirement Manager Agent       │
          │   ingest | confirm | reject | list  │
          └─────────────────────────────────────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │PostgreSQL│ │ Milvus   │ │Claude API│
      │  需求存储 │ │ 向量检索 │ │  LLM提取 │
      └──────────┘ └──────────┘ └──────────┘
```

### 4.2 目录结构

```
shared/services/feishu/
├── __init__.py              # 模块入口，init_feishu_gateway()
├── client.py                # FeishuClient - API 调用封装
├── router.py                # FastAPI 统一路由
├── handlers/
│   ├── __init__.py
│   ├── bot.py               # BotHandler - Bot 消息处理
│   ├── card.py              # CardHandler - 卡片回调处理
│   └── event.py             # EventHandler - 事件订阅处理
├── cards/
│   ├── __init__.py
│   ├── builder.py           # CardBuilder - 卡片构建器
│   └── requirement.py       # 需求相关卡片模板
└── tests/
    ├── test_client.py       # 17 tests ✅
    ├── test_cards.py        # 7 tests ✅
    ├── test_handlers.py     # 6 tests ✅
    └── test_router.py       # 2 tests ✅
```

### 4.3 关键组件

| 组件 | 职责 | 核心方法 |
|------|------|----------|
| FeishuClient | Token 管理、API 调用 | `get_access_token()`, `send_card()`, `verify_signature()` |
| BotHandler | 处理 @机器人 消息 | `handle_message()` |
| CardHandler | 处理卡片按钮回调 | `handle_action()` |
| EventHandler | 处理事件订阅 | `dispatch()`, `_handle_meeting_ended()` |
| CardBuilder | 构建消息卡片 | `set_header()`, `add_text()`, `add_action_buttons()`, `build()` |

---

## 5. 接口规格

### 5.1 Webhook 端点

```
POST /api/feishu/webhook
```

**请求头**:
| Header | 描述 |
|--------|------|
| X-Lark-Request-Timestamp | 请求时间戳 |
| X-Lark-Request-Nonce | 随机数 |
| X-Lark-Signature | 签名 |

**请求类型**:

1. **URL 验证** (首次配置)
```json
{
  "type": "url_verification",
  "challenge": "xxx"
}
```
响应: `{"challenge": "xxx"}`

2. **事件回调**
```json
{
  "type": "event_callback",
  "header": {"event_type": "vc.meeting.meeting_ended_v1"},
  "event": {...}
}
```

3. **卡片回调**
```json
{
  "type": "card_action",
  "action": {"tag": "button", "value": {...}},
  "operator": {"open_id": "ou_xxx"}
}
```

### 5.2 健康检查

```
GET /api/feishu/health

Response 200:
{
  "status": "healthy",
  "feishu_enabled": true,
  "token_valid": true,
  "bot_enabled": true,
  "event_enabled": true,
  "card_enabled": true
}
```

---

## 6. 配置说明

### 6.1 环境变量

```bash
# === 必填 ===
FEISHU_APP_ID=cli_xxxxx           # 应用 ID
FEISHU_APP_SECRET=xxxxx           # 应用密钥
FEISHU_ENABLED=true               # 启用飞书集成

# === 安全配置 (生产环境必填) ===
FEISHU_ENCRYPT_KEY=xxxxx          # 加密密钥
FEISHU_VERIFICATION_TOKEN=xxxxx   # 验证令牌
FEISHU_VERIFY_SIGNATURE=true      # 启用签名验证

# === 功能开关 ===
FEISHU_BOT_ENABLED=true           # 启用 Bot 功能
FEISHU_EVENT_ENABLED=true         # 启用事件订阅
FEISHU_CARD_ENABLED=true          # 启用卡片回调

# === 可选 ===
FEISHU_DEFAULT_CHAT_ID=oc_xxxxx   # 默认通知群
FEISHU_API_BASE_URL=https://open.feishu.cn/open-apis
FEISHU_TOKEN_REFRESH_BUFFER=300   # Token 提前刷新时间(秒)
```

### 6.2 飞书应用权限

| 权限 | 用途 | 必需 |
|------|------|:----:|
| `im:message:send_as_bot` | 发送消息 | ✅ |
| `im:message:receive_as_bot` | 接收消息 | ✅ |
| `im:chat:readonly` | 读取群信息 | ✅ |
| `vc:meeting:readonly` | 读取会议信息 | ✅ |
| `contact:user.base:readonly` | 读取用户信息 | ✅ |
| `calendar:calendar:readonly` | 读取日历 | Phase 3 |
| `docs:doc:create` | 创建文档 | Phase 3 |

---

## 7. Phase 3 实施计划

### 7.1 任务清单

| # | 任务 | 文件 | 验收标准 | 估计工作量 |
|---|------|------|----------|-----------|
| 3.1 | 日历事件订阅 | `handlers/event.py` | 日历变更触发处理 | M |
| 3.2 | 日历事件卡片 | `cards/calendar.py` | 会议提醒卡片正确渲染 | S |
| 3.3 | /list 命令 | `handlers/bot.py` | 返回待确认需求列表 | S |
| 3.4 | /export 命令 | `handlers/bot.py` | 生成 PRD 文档链接 | M |
| 3.5 | 文档 API 集成 | `client.py` | 能创建飞书文档 | M |
| 3.6 | PRD 模板 | `cards/prd_template.py` | PRD 格式正确 | S |
| 3.7 | 批量选择卡片 | `cards/batch.py` | 多选 UI 正常 | M |
| 3.8 | 批量操作逻辑 | `handlers/card.py` | 批量确认/拒绝生效 | M |
| 3.9 | 单元测试 | `tests/` | 覆盖率 > 80% | M |
| 3.10 | 集成测试 | `tests/` | E2E 流程通过 | L |

### 7.2 依赖关系

```
3.1 ──▶ 3.2
3.3 ──┬──▶ 3.7 ──▶ 3.8
      │
3.4 ──┴──▶ 3.5 ──▶ 3.6
              │
3.9 ◀────────┴──▶ 3.10
```

### 7.3 代码示例

#### 日历事件处理 (Task 3.1)

```python
# shared/services/feishu/handlers/event.py

CALENDAR_KEYWORDS = ["需求", "产品", "review", "PRD", "评审"]

async def _handle_calendar_changed(self, data: dict) -> dict:
    """处理日历变更事件"""
    event = data.get("event", {})
    calendar_event = event.get("calendar_event", {})

    title = calendar_event.get("summary", "")
    start_time = calendar_event.get("start_time", {}).get("timestamp")
    attendees = calendar_event.get("attendees", [])

    # 过滤关键词
    if not any(kw in title for kw in CALENDAR_KEYWORDS):
        return {"code": 0}

    # 发送提醒卡片
    card = build_calendar_reminder_card(title, start_time, attendees)
    await self.client.send_card(
        receive_id=settings.feishu_default_chat_id,
        receive_id_type="chat_id",
        card=card
    )

    return {"code": 0}
```

#### /list 命令 (Task 3.3)

```python
# shared/services/feishu/handlers/bot.py

async def _send_list(self, chat_id: str, message_id: str) -> None:
    """发送待确认需求列表"""
    # 获取待确认需求
    requirements = await self.agent.list_requirements(
        status="pending",
        limit=10
    )

    if not requirements:
        await self.client.reply_message(
            message_id,
            "📋 当前没有待确认的需求"
        )
        return

    # 构建列表卡片
    card = build_requirement_list_card(requirements)
    await self.client.send_card(
        receive_id=chat_id,
        receive_id_type="chat_id",
        card=card
    )
```

#### PRD 导出 (Task 3.4, 3.5)

```python
# shared/services/feishu/client.py

async def create_doc(
    self,
    folder_token: str,
    title: str,
    content: str
) -> str:
    """
    创建飞书文档

    Args:
        folder_token: 目标文件夹 Token
        title: 文档标题
        content: 文档内容 (富文本 JSON)

    Returns:
        doc_url: 文档链接
    """
    token = await self.get_access_token()
    url = f"{self.base_url}/docx/v1/documents"

    payload = {
        "folder_token": folder_token,
        "title": title,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    doc_token = data["data"]["document"]["document_id"]

    # 追加内容
    await self._append_doc_content(doc_token, content)

    return f"https://xxx.feishu.cn/docs/{doc_token}"
```

---

## 8. 测试策略

### 8.1 测试金字塔

```
                   ┌───────┐
                   │  E2E  │  ← 真实飞书沙箱 (手动)
                 ┌─┴───────┴─┐
                 │  集成测试  │  ← Mock 飞书 API
               ┌─┴───────────┴─┐
               │    单元测试    │  ← 28 tests ✅
               └───────────────┘
```

### 8.2 当前测试覆盖

| 测试文件 | 测试数 | 状态 |
|----------|:------:|:----:|
| test_client.py | 17 | ✅ |
| test_cards.py | 7 | ✅ |
| test_handlers.py | 6 | ✅ |
| test_router.py | 2 | ✅ |
| **Total** | **32** | ✅ |

### 8.3 运行测试

```bash
# 运行所有飞书测试
.venv/bin/python -m pytest shared/services/feishu/tests/ -v

# 运行特定测试
.venv/bin/python -m pytest shared/services/feishu/tests/test_handlers.py -v

# 带覆盖率
.venv/bin/python -m pytest shared/services/feishu/tests/ --cov=shared/services/feishu
```

---

## 9. 部署检查清单

### 9.1 飞书应用配置

- [ ] 在 https://open.feishu.cn/app 创建应用
- [ ] 启用机器人能力
- [ ] 配置事件订阅 URL: `https://your-domain/api/feishu/webhook`
- [ ] 添加事件订阅:
  - [ ] `im.message.receive_v1`
  - [ ] `vc.meeting.meeting_ended_v1`
- [ ] 配置消息卡片回调 URL
- [ ] 申请并获批所需权限
- [ ] 发布应用

### 9.2 环境配置

- [ ] 设置 FEISHU_APP_ID
- [ ] 设置 FEISHU_APP_SECRET
- [ ] 设置 FEISHU_ENCRYPT_KEY
- [ ] 设置 FEISHU_ENABLED=true
- [ ] 设置 FEISHU_VERIFY_SIGNATURE=true

### 9.3 验证

```bash
# 1. 启动服务
python -m agents.requirement_manager.app.main

# 2. 检查健康状态
curl http://localhost:8000/api/feishu/health

# 期望响应:
# {"status": "healthy", "feishu_enabled": true, "token_valid": true, ...}

# 3. 在飞书中 @机器人 发送 /help
# 期望: 收到帮助卡片
```

---

## 10. 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 飞书 API 变更 | 高 | 低 | 抽象 Client 层，版本锁定 |
| Token 刷新失败 | 高 | 低 | 断路器 + 重试 + 降级 |
| 签名验证绕过 | 高 | 低 | 强制生产环境验证 |
| 会议无纪要 | 中 | 中 | 优雅跳过，不发卡片 |
| 卡片渲染异常 | 低 | 低 | 预览测试 + 降级文本 |

---

## 11. 变更历史

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-01-23 | v1.0 | 初始 PRD，Phase 1-2 已完成 | Claude |

---

## 附录 A: 飞书 API 参考

- [消息 API](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create)
- [卡片构建器](https://open.feishu.cn/document/ukTMukTMukTM/uYzM3QjL2MzN04iNzcDN)
- [事件订阅](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)
- [会议事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/meeting_ended)
- [日历事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/calendar-v4/calendar-event/events/changed)
- [文档 API](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN)

## 附录 B: Ralph-Claude-Code 使用说明

本 PRD 设计为可被 `ralph-import` 工具解析，生成：

- `PROMPT.md`: 开发指令
- `@fix_plan.md`: 优先任务列表
- 技术规格文件

**使用方式**:
```bash
# 导入 PRD
ralph-import docs/specs/feishu-integration-prd.md

# 启动 Ralph 开发循环
ralph start --spec feishu-integration
```

---

*本文档遵循大厂 PRD 规范，适用于 AI 自动化开发流程。*
