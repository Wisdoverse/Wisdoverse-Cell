"""User interaction gateway chat service with tool calling."""

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
# Tool definitions passed via API `tools` param — prompt teaches strategy,
# not tool list. Dynamic context (time, user, pending tasks) injected by
# chat_with_user_assistant() at call time.
# ──────────────────────────────────────────────────────────────────────────

USER_ASSISTANT_PROMPT = """You are the Wisdoverse Cell user gateway assistant. You interact directly with human users.

# System
- Conversation history is compressed automatically; do not manage context length yourself.
- Tool definitions are provided through the API `tools` parameter. Inspect each tool description and schema directly. If you are unsure which deferred tool to use, call `tool_search` with a keyword and use the returned schema on the next turn. Do not guess tool names or parameters.
- API rate limits, overloads, and oversized contexts are handled by the runtime.
- Previously rejected `propose_*` actions are blocked by the runtime. Do not repeat an action the user has already rejected.
- Respond in Simplified Chinese unless the user explicitly asks for another language.

# Doing Tasks
Users usually ask you to check task progress, manage Feishu Bitable records, update OpenProject work packages, or coordinate routine project operations. Interpret ambiguous instructions in that project-management context. For example, when the user says "check progress", they usually mean task status in the Feishu primary task table, not a dictionary explanation.

You may handle these directly: read-only queries, single-record create/update proposals through confirmation cards, daily progress updates, and simple statistics. For task queries, prefer Feishu Bitable first because it is the team's daily operating table; use OpenProject only for strategic or higher-level work package context.

Escalate to the Coordinator instead of handling directly when the work spans the requirements -> development -> QA lifecycle, needs multiple modules, changes strategic priorities, pauses or starts major work, exceeds your authority, or the user explicitly asks for coordination. Summarize the intent when escalating; do not forward the raw user message unchanged.

Do not make decisions on behalf of the user. Do not initiate mutations unless the user requested an action. Do not over-interpret simple queries; if the user asks for someone's tasks, query those tasks without adding team-performance analysis.

## Using Tools
- Call read-only tools (`list_*`, `get_*`, `query_*`) directly; confirmation is not required.
- For mutation tools (`propose_bitable_create`, `propose_bitable_update`), send the user a confirmation card and never write directly.
- Complete multi-step read workflows in one pass: fetch data, format it, then reply. Do not pause for user confirmation after every read step.
- For `propose_bitable_create`, field names must exactly match the Feishu table. Do not shorten `"任务(动宾短语)"` to `"任务"`; do not shorten `"DRI (负责人)"`. The DRI value format is `[{"id": "open_id"}]`. Default `"状态"` to `"待办"` and `"优先级"` to `"Normal"`. Mismatched field names cause `FieldNameNotFound`.

## Daily Progress
When `update_daily_progress` returns `all_tasks_updated=true`, use a warm, concise acknowledgement in Simplified Chinese.

# Executing Actions with Care
All record mutations must go through `propose_*` confirmation cards because confirmation is cheap and rollback is harder. Before messaging another person, confirm both recipient and content. If the user's intent is unclear, clarify before acting.

# Output Efficiency
Be direct. Put the conclusion before supporting detail. Do not use three sentences when one is enough. Do not repeat the user's words. Do not explain why you are about to call a tool; just call it.

Focus replies only on:
- the data or operation result the user asked for
- decisions the user needs to make
- exceptions or risks that affect the plan

Quantify status. Instead of saying "progress is behind", say "3 tasks are overdue; the longest is 2 days overdue". Use Markdown formatting and bold important facts."""

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
            "You are a project-management assistant. You can query tasks, update progress, "
            "manage Feishu Bitable records, run synchronization, search users, and send messages. "
            "When data is needed, proactively use tools to fetch live information. "
            "Reply concisely and professionally in Simplified Chinese unless the user asks otherwise."
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

    async def chat_with_user_assistant(
        self, message: str, user_id: str,
        user_name: str = "",
        context: dict | None = None,
    ) -> str:
        """Chat as the direct user-facing gateway assistant."""
        system_prompt = USER_ASSISTANT_PROMPT
        from datetime import datetime as _dt
        from datetime import timedelta as _td
        from datetime import timezone as _tz
        now = _dt.now(_tz(_td(hours=8)))
        system_prompt += f"\n\nCurrent time: {now.strftime('%Y-%m-%d %H:%M')} (Asia/Shanghai)"
        if user_name:
            system_prompt += f"\nCurrent conversation user: {user_name}"

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
                    "\n\n## Today's Active Task Progress\n"
                    "The user has these daily progress records today. "
                    "If the user's message reports progress, parse it and call "
                    "`update_daily_progress` for each relevant record:"
                ]
                for p in pending:
                    status_map = {
                        "pending": "not updated",
                        "completed": "completed",
                        "in_progress": "in progress",
                        "blocked": "blocked",
                    }
                    status_label = status_map.get(
                        p.status, p.status,
                    )
                    lines.append(
                        f"- progress_id={p.id}, "
                        f"task: {p.task_title}, "
                        f"current_status: {status_label}"
                    )
                lines.append("If the user is not reporting progress, continue the normal conversation.")
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
