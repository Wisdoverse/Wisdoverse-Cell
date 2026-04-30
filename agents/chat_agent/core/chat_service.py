"""Chat Service - Claude AI 聊天服务（Tool Calling + PM 人设）"""

import json

from shared.config import settings
from shared.infra.audit_log import AuditAction, audit_log
from shared.infra.context_compressor import ContextCompressor, ContextCompressorConfig
from shared.infra.conversation_engine import (
    ConversationConfig,
    ConversationEngine,
    ToolExecutionEvent,
)
from shared.infra.denial_tracker import DenialTracker
from shared.infra.llm_gateway import llm_gateway
from shared.infra.tool_registry import ToolRegistry, build_tool
from shared.infra.tool_validator import ToolValidationError, ToolValidator
from shared.utils.logger import get_logger

from ..app.metrics import TOOL_CALLS
from ..db.database import db_manager
from ..db.repository import ConversationRepository, DailyProgressRepository
from .tools import TOOLS, ToolExecutor, _get_redis, _tool_registry

logger = get_logger("chat_agent.chat")

# ── System Prompt ─────────────────────────────────────────────────────────
# chat_agent 角色 = 前台 (见 coordinator-agent-design.md §2)
# 简单查询直接回，复杂指令升级给 Coordinator。
# 不是 CEO，不做跨 Agent 决策。
#
# Tool definitions passed via API `tools` param — prompt teaches strategy,
# not tool list. Dynamic context (time, user, pending tasks) injected by
# chat_with_pm_persona() at call time.
# ──────────────────────────────────────────────────────────────────────────

PM_PERSONA_PROMPT = """你是 Wisdoverse Cell 的用户助手，直接面对人类用户，用中文交流。

# System
- 对话历史会自动压缩，你不需要管理上下文长度。放心进行多轮对话。
- 工具定义已通过 API 提供，你可以直接查看每个工具的描述和参数。不熟悉的工具用 tool_search 搜索，下一轮即可调用。不要猜测工具名或参数。
- API 限流、过载、上下文超长由系统自动处理，你不需要担心。
- 用户拒绝过的 propose_* 操作会被系统自动拦截。不要重复提议已被拒绝的操作。

# Doing Tasks
用户主要向你询问任务进度、管理飞书表格、更新 OP 任务等。遇到不明确的指令，结合项目管理场景理解。例如用户说"查一下进度"，是在问飞书主表的任务状态，不是让你解释"进度"这个词。

你可以直接处理：查询、单条新建/更新（走卡片确认）、每日进展、简单统计。查询时**优先飞书多维表格**（员工日常使用的主表），仅需战略层面信息时才用 OpenProject。

你不直接处理，升级给 Coordinator：涉及需求→开发→QA 全链路、需要多个 Agent 协作、战略级指令（暂停/启动/优先级大调整）、你判断超出自己能力范围的、用户明确要求协调的。升级时提炼意图，不要原样转发用户消息。

不要替用户做决定。不要在用户没要求时主动发起变更操作。不要过度解读简单查询——用户问"小明的任务"就查任务，不需要额外分析团队效能。

## 使用工具
- 查询类工具（list_*、get_*、query_*）直接调用，不需要确认
- 变更类工具（propose_bitable_create、propose_bitable_update）发确认卡片给用户，绝不直接写入
- 多步查询一口气串联完成（查数据 → 格式化 → 回复），不要每步等用户确认
- propose_bitable_create 字段名必须和飞书表格完全一致。"任务(动宾短语)"不能简写为"任务"，"DRI (负责人)"不能简写。DRI 格式 `[{"id": "open_id"}]`。状态默认"待办"，优先级默认"Normal"。字段名不匹配会报 FieldNameNotFound。

## 每日进展
update_daily_progress 返回 all_tasks_updated=true 时，用温暖鼓励的语气，如"今天的任务都跟进到位了，辛苦了！💪"

# Executing Actions with Care
变更操作（新建/更新/删除记录）必须走 propose_* 确认卡片——成本低，撤销难。发消息给其他人前先确认收件人和内容。不确定用户意图时先澄清再行动。

# Output Efficiency
直奔主题。先结论后分析。一句话能说清不用三句。不要重复用户说过的话。不要解释你为什么要调用某个工具——直接调就行。

回复只聚焦在：
- 用户要的数据或操作结果
- 需要用户做决定的事
- 影响计划的异常或风险

量化：不说"进度落后"，说"3 个任务超期，最长超 2 天"。用 Markdown 格式化，加粗关键信息。"""

MAX_TOOL_CALLS = 10
MAX_HISTORY = 40

_DEFERRED_TOOL_NAMES = {
    "sync_now",
    "add_bitable_field",
    "list_card_operations",
    "search_feishu_user",
    "send_feishu_message",
}


def _build_tool_registry() -> ToolRegistry:
    """Build a ToolRegistry from the TOOLS list with deferred flags."""
    registry = ToolRegistry()
    for tool_def in TOOLS:
        name = tool_def["name"]
        handler = _tool_registry.get(name)
        if handler is None:
            continue
        tool = build_tool(
            name=name,
            description=tool_def.get("description", ""),
            handler=handler,
            should_defer=name in _DEFERRED_TOOL_NAMES,
        )
        registry.register(tool)
        registry.register_raw_schema(name, tool_def)
    return registry


class ChatService:
    """Claude chat service with tool calling support."""

    def __init__(self):
        self._llm = llm_gateway
        self._max_history = MAX_HISTORY
        self._registry = _build_tool_registry()
        self._tool_validator = ToolValidator(
            registered_tools=self._registry.to_anthropic_schemas(),
        )
        self._denial_tracker = DenialTracker(redis=_get_redis())
        self._compressor = ContextCompressor(
            ContextCompressorConfig(
                l1_threshold_tokens=40_000,
                l2_threshold_tokens=70_000,
                keep_recent_messages=10,
                keep_recent_tool_results=5,
                summary_model=settings.summary_model,
                agent_id="chat-agent",
            ),
            llm=self._llm,
        )

    async def _get_history(self, user_id: str) -> list[dict]:
        async with db_manager.session() as session:
            repo = ConversationRepository(session)
            return await repo.get_by_user(user_id) or []

    async def _save_history(self, user_id: str, messages: list[dict]):
        if len(messages) > self._max_history:
            messages = messages[-self._max_history:]
            messages = self._strip_orphaned_tool_messages(messages)
        async with db_manager.session() as session:
            repo = ConversationRepository(session)
            await repo.save(user_id, messages)

    async def chat(
        self,
        message: str,
        user_id: str,
        system_prompt: str | None = None,
        context: dict | None = None,
    ) -> str:
        """发送消息并获取回复，支持 Tool Calling via ConversationEngine."""
        history = await self._get_history(user_id)

        # Token-aware context compression (MicroCompact + L1 + L2)
        compress_result = await self._compressor.compress_if_needed(history)
        history = compress_result.messages

        if len(history) > self._max_history:
            history = history[-self._max_history:]
            history = self._strip_orphaned_tool_messages(history)

        default_system = (
            "你是一个项目管理助手，可以帮助用户查询项目任务、更新进度、管理飞书表格、执行同步、搜索用户并发送消息。"
            "当需要数据时，请主动使用工具获取实时信息。请用简洁、专业的中文回答。"
        )

        # Chat-specific state for tool_search deferred loading
        active_deferred: set[str] = set()

        # Build tool executor callback wrapping all chat-specific logic
        async def _chat_tool_executor(tool_name: str, tool_input: dict, ctx: dict) -> str:
            # tool_search: deferred tool loading
            if tool_name == "tool_search":
                query = tool_input.get("query", "")
                search_results = self._registry.search_tools(query)
                for r in search_results:
                    active_deferred.add(r["name"])
                self._tool_validator.add_tools(
                    {r["name"] for r in search_results},
                )
                return json.dumps(search_results, ensure_ascii=False)

            # E4: Denial check before propose_bitable_* tools
            if tool_name.startswith("propose_bitable_"):
                action_type = tool_name.replace("propose_bitable_", "")
                table_id = tool_input.get("table_id", "")
                try:
                    denial = await self._denial_tracker.is_denied(
                        agent_id="chat-agent",
                        user_id=user_id,
                        action_type=action_type,
                        table_id=table_id,
                    )
                except Exception as exc:
                    logger.warning("denial_check_failed", error=str(exc))
                    denial = None
                if denial:
                    denied_at = denial.get("denied_at", "")
                    raise ToolValidationError(
                        f"此操作已被用户拒绝（{denied_at}），请换个方案。"
                    )

            # Validate before execution
            try:
                self._tool_validator.validate_tool_use(
                    {"name": tool_name, "input": tool_input},
                )
            except ToolValidationError as exc:
                audit_log(
                    action=AuditAction.TOOL_EXECUTED,
                    agent_id="chat-agent",
                    detail={
                        "tool": tool_name,
                        "rejected": True,
                        "reason": str(exc),
                    },
                )
                raise

            TOOL_CALLS.labels(tool_name=tool_name).inc()
            logger.info("tool_call", tool=tool_name)
            result = await ToolExecutor.execute(
                tool_name, tool_input, context=context,
            )
            audit_log(
                action=AuditAction.TOOL_EXECUTED,
                agent_id="chat-agent",
                detail={"tool": tool_name, "success": True},
            )
            return result

        try:
            config = ConversationConfig(
                model=settings.chat_model,
                system_prompt=system_prompt or default_system,
                tools=lambda: self._registry.to_anthropic_schemas(active_deferred),
                max_tool_calls=MAX_TOOL_CALLS,
                agent_id="chat-agent",
            )
            engine = ConversationEngine(
                config,
                llm_gateway=self._llm,
                compressor=self._compressor,
                tool_executor=_chat_tool_executor,
                messages=history,
            )

            card_sent = False
            text = ""
            async for event in engine.run(message):
                if isinstance(event, ToolExecutionEvent):
                    if event.tool_name.startswith("propose_"):
                        card_sent = True
                # Capture the final text from TurnCompleteEvent or LLMResponseEvent
                if hasattr(event, "text") and event.text:
                    text = event.text

            # Card was sent → suppress duplicate text
            if card_sent:
                text = ""

            # Persist history
            final_messages = engine.messages
            if not text and not card_sent:
                # Replace engine's placeholder with a descriptive one
                if final_messages and final_messages[-1].get("role") == "assistant":
                    final_messages[-1]["content"] = "（已达到工具调用上限）"
            elif card_sent and final_messages and final_messages[-1].get("role") == "assistant":
                final_messages[-1]["content"] = "[card_sent]"

            if len(final_messages) > self._max_history:
                final_messages = final_messages[-self._max_history:]
                final_messages = self._strip_orphaned_tool_messages(final_messages)

            await self._save_history(user_id, final_messages)
            return text

        except Exception as e:
            logger.error("chat_error", error=str(e))
            if history and history[-1]["role"] == "user":
                history.pop()
            raise

    async def chat_with_pm_persona(
        self, message: str, user_id: str,
        user_name: str = "",
        context: dict | None = None,
    ) -> str:
        """使用 PM 人设聊天"""
        system_prompt = PM_PERSONA_PROMPT
        from datetime import datetime as _dt
        from datetime import timedelta as _td
        from datetime import timezone as _tz
        now = _dt.now(_tz(_td(hours=8)))
        system_prompt += f"\n\n当前时间：{now.strftime('%Y-%m-%d %H:%M')}（Asia/Shanghai）"
        if user_name:
            system_prompt += f"\n当前对话用户：{user_name}"

        # Pass user_id via context (not system prompt) for tool use — SEC-003
        merged_context = {**(context or {}), "user_id": user_id}

        # Check if user has pending daily progress
        progress_context = ""
        try:
            async with db_manager.session() as session:
                repo = DailyProgressRepository(session)
                pending = await repo.get_pending(user_id, now.date())
            if pending:
                lines = [
                    "\n\n## 今日活跃任务进展\n"
                    "该用户今天有以下任务进展记录，"
                    "请根据用户回复解析并调用"
                    " update_daily_progress 工具逐条更新："
                ]
                for p in pending:
                    status_map = {
                        "pending": "未更新",
                        "completed": "已完成",
                        "in_progress": "进行中",
                        "blocked": "阻塞",
                    }
                    status_label = status_map.get(
                        p.status, p.status,
                    )
                    lines.append(
                        f"- progress_id={p.id}, "
                        f"任务: {p.task_title}, "
                        f"当前状态: {status_label}"
                    )
                lines.append("如果用户说的不是进展汇报，则正常对话。")
                progress_context = "\n".join(lines)
        except Exception:
            pass

        return await self.chat(
            message=message,
            user_id=user_id,
            system_prompt=system_prompt + progress_context,
            context=merged_context,
        )

    async def clear_history(self, user_id: str) -> None:
        async with db_manager.session() as session:
            repo = ConversationRepository(session)
            await repo.clear(user_id)

    @staticmethod
    def _strip_orphaned_tool_messages(messages: list[dict]) -> list[dict]:
        """Remove leading messages that would cause orphaned tool_result API errors."""
        while messages:
            msg = messages[0]
            if msg["role"] == "assistant":
                messages.pop(0)
                continue
            content = msg.get("content")
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            ):
                messages.pop(0)
                continue
            break
        return messages
