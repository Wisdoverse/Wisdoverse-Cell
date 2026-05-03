"""Tool definitions for Claude Tool Calling"""
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.config import settings
from shared.core import (
    BitableTablePort,
    FeishuContactLookupPort,
    FeishuMessengerPort,
    OpenProjectWorkPackagePort,
)
from shared.utils.logger import get_logger

from .card_ports import ToolCardRendererPort
from .ops_logger import record_op

# Redis for storing pending operation fields (SEC-103)
_redis: aioredis.Redis | None = None
_PENDING_OP_TTL = 1800  # 30 minutes


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def _store_pending_op(data: dict) -> str:
    """Store pending operation fields in Redis, return the action_id."""
    action_id = str(uuid.uuid4())
    r = _get_redis()
    await r.set(f"pending_op:{action_id}", json.dumps(data, ensure_ascii=False), ex=_PENDING_OP_TTL)
    return action_id


async def get_pending_op(action_id: str) -> dict | None:
    """Retrieve pending operation fields from Redis by action_id."""
    r = _get_redis()
    raw = await r.get(f"pending_op:{action_id}")
    if raw is None:
        return None
    return json.loads(raw)

logger = get_logger("chat_agent.tools")


@dataclass(frozen=True)
class ToolDependencies:
    """External platform ports used by tool handlers."""

    op_client: OpenProjectWorkPackagePort
    bitable: BitableTablePort
    messenger: FeishuMessengerPort
    contact_lookup: FeishuContactLookupPort
    card_renderer: ToolCardRendererPort


_tool_dependencies: ToolDependencies | None = None


def configure_tool_dependencies(dependencies: ToolDependencies | None) -> None:
    """Configure tool-handler dependencies at the service entry point."""
    global _tool_dependencies
    _tool_dependencies = dependencies


def _require_dependencies() -> ToolDependencies:
    if _tool_dependencies is None:
        raise RuntimeError("tool dependencies are not configured")
    return _tool_dependencies


def _format_field_value(v):
    """Format a bitable field value for human-readable card display."""
    if v is None:
        return ""
    # List of dicts → extract names/text
    if isinstance(v, list) and v and isinstance(v[0], dict):
        names = []
        for item in v:
            name = item.get("name") or item.get("text") or item.get("id", "")
            if name:
                names.append(str(name))
        return "、".join(names) if names else str(v)
    # Timestamp in ms (10+ digits, reasonable date range)
    if isinstance(v, (int, float)) and 1_000_000_000_000 < v < 3_000_000_000_000:
        try:
            dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    return str(v)


def _format_fields_display(fields: dict) -> str:
    """Format fields dict into readable markdown lines for card display."""
    return "\n".join(
        f"- **{k}**: {_format_field_value(v)}"
        for k, v in fields.items()
        if v is not None
    )

# Claude Tool Calling tool definitions
TOOLS = [
    {
        "name": "get_work_packages",
        "description": (
            "Get OpenProject work packages for strategic-level company work "
            "(Epic/Feature). Use this only for high-level context; prefer "
            "`list_bitable_records` for daily task queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
                "limit": {"type": "integer", "description": "Maximum number of results", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_work_package_detail",
        "description": "Get details for a single OpenProject work package.",
        "input_schema": {
            "type": "object",
            "properties": {"work_package_id": {"type": "integer", "description": "Work package ID"}},
            "required": ["work_package_id"],
        },
    },
    {
        "name": "update_work_package_progress",
        "description": "Update the progress percentage for an OpenProject work package.",
        "input_schema": {
            "type": "object",
            "properties": {
                "work_package_id": {"type": "integer", "description": "Work package ID"},
                "progress": {"type": "integer", "description": "Progress percentage from 0 to 100"},
            },
            "required": ["work_package_id", "progress"],
        },
    },
    {
        "name": "list_bitable_records",
        "description": (
            "List Feishu Bitable records from the team's primary daily task table. "
            "This table contains atomic breakdowns of OpenProject work. "
            "Prefer this tool when the user asks about tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Maximum number of results", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "list_member_records",
        "description": (
            "List Feishu member-table records, including team member names, "
            "departments, and linked tasks. Use this when the user asks about "
            "team members or ownership."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Maximum number of results", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "query_pm_table",
        "description": (
            "Query secondary Feishu Bitable project-management tables. "
            "Available tables: categories (category board and AI summary), "
            "weekly_report (weekly report)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Table name: categories or weekly_report",
                    "enum": ["categories", "weekly_report"],
                },
                "limit": {"type": "integer", "description": "Maximum number of results", "default": 20},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "propose_bitable_update",
        "description": (
            "Propose an update to a Feishu Bitable record. This sends a "
            "confirmation card to the user; the update runs only after the "
            "user confirms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID"},
                "fields": {"type": "object", "description": "Fields to update"},
                "table_id": {
                    "type": "string",
                    "description": "Table ID from query results. Required for non-default tables.",
                },
            },
            "required": ["record_id", "fields"],
        },
    },
    {
        "name": "propose_bitable_create",
        "description": (
            "Propose creating a Feishu Bitable record. This sends a "
            "confirmation card; the record is created only after user "
            "confirmation. Primary task table field names are: "
            "任务(动宾短语), 状态, DRI (负责人), 优先级, 计划完成日期, 所属大类, 阻塞原因."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "Fields for the new record",
                },
                "table_id": {"type": "string", "description": "Table ID. Defaults to the primary task table if omitted."},
            },
            "required": ["fields"],
        },
    },
    {
        "name": "add_bitable_field",
        "description": (
            "Add a field (column) to a Feishu Bitable table. Field types: "
            "1=text, 2=number, 3=single select, 4=multi select, 5=date, "
            "7=checkbox, 11=person, 15=url."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field_name": {"type": "string", "description": "Field name"},
                "field_type": {
                    "type": "integer",
                    "description": "Field type. Default is 1=text.",
                    "default": 1,
                },
                "table_id": {"type": "string", "description": "Table ID. Defaults to the primary task table if omitted."},
            },
            "required": ["field_name"],
        },
    },
    {
        "name": "list_bitable_fields",
        "description": "List all fields in a Feishu Bitable table, including field names and types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "Table ID. Defaults to the primary task table if omitted."},
            },
            "required": [],
        },
    },
    {
        "name": "sync_now",
        "description": "Run one synchronization immediately.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_card_operations",
        "description": (
            "List confirmation-card operation audit logs. Use this for questions "
            "such as how many tasks were created this week, who rejected the most "
            "changes, or a user's recent operations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Filter by user open_id"},
                "action": {
                    "type": "string",
                    "description": "Filter by operation type",
                    "enum": ["propose_create", "confirm_create", "reject_create",
                             "propose_update", "confirm_update", "reject_update"],
                },
                "limit": {"type": "integer", "description": "Maximum number of results", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "update_daily_progress",
        "description": "Update an employee's daily task progress. After parsing an employee reply, call this tool once per progress record that should be updated.",
        "input_schema": {
            "type": "object",
            "properties": {
                "progress_id": {"type": "integer", "description": "Progress record ID"},
                "status": {
                    "type": "string",
                    "description": "Task status",
                    "enum": ["completed", "in_progress", "blocked"],
                },
                "note": {"type": "string", "description": "Progress note"},
            },
            "required": ["progress_id", "status"],
        },
    },
    {
        "name": "search_feishu_user",
        "description": "Search Feishu users by email or 11-digit phone number.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search keyword"}},
            "required": ["query"],
        },
    },
    {
        "name": "send_feishu_message",
        "description": "Send a Feishu message to a specific user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Recipient open_id"},
                "message": {"type": "string", "description": "Message content"},
            },
            "required": ["user_id", "message"],
        },
    },
]


# Tool registry
_tool_registry: dict[str, Callable] = {}

# Tools that always need context forwarded
_context_tools = {
    "add_bitable_field",
    "propose_bitable_update",
    "propose_bitable_create",
    "search_feishu_user",
    "send_feishu_message",
}


def register_tool(name: str):
    """Decorator to register a tool handler function."""
    def decorator(func):
        _tool_registry[name] = func
        return func
    return decorator


def _has_sensitive_action_approval(context: dict | None, action: str) -> bool:
    context = context or {}
    approved = context.get("approved_sensitive_actions", [])
    if isinstance(approved, str):
        approved = [approved]
    return action in set(approved)


class ToolExecutor:
    """Execute tool calls via the module-level registry."""

    @staticmethod
    async def execute(tool_name: str, tool_input: dict, context: dict | None = None) -> str:
        """Execute a tool by name.

        Args:
            tool_name: Tool function name.
            tool_input: Arguments from Claude.
            context: Optional runtime context (user_id, chat_id, chat_type).
        """
        handler = _tool_registry.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
        try:
            if tool_name in _context_tools:
                return await handler(context=context or {}, **tool_input)
            return await handler(**tool_input)
        except Exception as e:
            logger.error(
                "tool_exec_error",
                tool=tool_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            return json.dumps({"error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool handler functions — each registered via @register_tool
# ---------------------------------------------------------------------------


@register_tool("get_work_packages")
async def _handle_get_work_packages(project_id: int = None, limit: int = 10) -> str:
    op = _require_dependencies().op_client
    wps = await op.get_work_packages(project_id=project_id, page_size=limit)
    result = []
    for wp in wps:
        result.append({
            "id": wp.get("id"),
            "subject": wp.get("subject"),
            "status": wp.get("_links", {}).get("status", {}).get("title", ""),
            "progress": wp.get("percentageDone", 0),
            "due_date": wp.get("dueDate"),
            "assignee": wp.get("_links", {}).get("assignee", {}).get("title", "未分配"),
        })
    return json.dumps({"work_packages": result, "total": len(result)}, ensure_ascii=False)


@register_tool("get_work_package_detail")
async def _handle_get_work_package_detail(work_package_id: int) -> str:
    op = _require_dependencies().op_client
    wp = await op.get_work_package(work_package_id)
    return json.dumps({
        "id": wp.get("id"),
        "subject": wp.get("subject"),
        "status": wp.get("_links", {}).get("status", {}).get("title", ""),
        "progress": wp.get("percentageDone", 0),
        "due_date": wp.get("dueDate"),
        "assignee": wp.get("_links", {}).get("assignee", {}).get("title", "未分配"),
    }, ensure_ascii=False)


@register_tool("update_work_package_progress")
async def _handle_update_work_package_progress(work_package_id: int, progress: int) -> str:
    if not 0 <= progress <= 100:
        return json.dumps({"error": "进度必须在 0-100 之间"}, ensure_ascii=False)
    op = _require_dependencies().op_client
    await op.update_work_package(work_package_id, {"percentageDone": progress})
    return json.dumps({"success": True, "message": f"进度已更新为 {progress}%"}, ensure_ascii=False)


@register_tool("list_bitable_records")
async def _handle_list_bitable_records(limit: int = 20) -> str:
    from shared.config import settings as _settings
    bitable = _require_dependencies().bitable
    result = await bitable.list_records(page_size=limit)
    table_id = _settings.feishu_bitable_table_id
    records = [
        {"record_id": r["record_id"], "table_id": table_id, "fields": r["fields"]}
        for r in result.get("items", [])
    ]
    return json.dumps({"records": records, "total": len(records)}, ensure_ascii=False)


@register_tool("list_member_records")
async def _handle_list_member_records(limit: int = 20) -> str:
    from shared.config import settings as _settings
    table_id = _settings.feishu_bitable_member_table_id
    bitable = _require_dependencies().bitable
    result = await bitable.list_records(
        app_token=_settings.feishu_bitable_app_token,
        table_id=table_id,
        page_size=limit,
    )
    records = [
        {"record_id": r["record_id"], "table_id": table_id, "fields": r["fields"]}
        for r in result.get("items", [])
    ]
    return json.dumps({"records": records, "total": len(records)}, ensure_ascii=False)


@register_tool("query_pm_table")
async def _handle_query_pm_table(table_name: str, limit: int = 20) -> str:
    from shared.config import settings as _settings
    bitable = _require_dependencies().bitable
    table_map = {
        "categories": _settings.feishu_bitable_category_table_id,
        "weekly_report": _settings.feishu_bitable_report_table_id,
    }
    table_id = table_map.get(table_name)
    if not table_id:
        return json.dumps({"error": f"未知表名: {table_name}"}, ensure_ascii=False)
    result = await bitable.list_records(
        app_token=_settings.feishu_bitable_app_token,
        table_id=table_id,
        page_size=limit,
    )
    records = [
        {"record_id": r["record_id"], "table_id": table_id, "fields": r["fields"]}
        for r in result.get("items", [])
    ]
    return json.dumps(
        {"table": table_name, "records": records, "total": len(records)},
        ensure_ascii=False,
    )


@register_tool("add_bitable_field")
async def _handle_add_bitable_field(
    field_name: str, field_type: int = 1, table_id: str = "", context: dict | None = None,
) -> str:
    if not _has_sensitive_action_approval(context, "add_bitable_field"):
        return json.dumps(
            {
                "error": (
                    "此操作会修改飞书多维表格结构，需要技术审批后由受控流程执行。"
                )
            },
            ensure_ascii=False,
        )
    kwargs = {"table_id": table_id} if table_id else {}
    bitable = _require_dependencies().bitable
    result = await bitable.create_field(field_name, field_type, **kwargs)
    return json.dumps({"success": True, **result}, ensure_ascii=False)


@register_tool("list_bitable_fields")
async def _handle_list_bitable_fields(table_id: str = "") -> str:
    kwargs = {"table_id": table_id} if table_id else {}
    bitable = _require_dependencies().bitable
    fields = await bitable.list_fields(**kwargs)
    return json.dumps({"fields": fields, "total": len(fields)}, ensure_ascii=False)


@register_tool("list_card_operations")
async def _handle_list_card_operations(user_id: str = "", action: str = "", limit: int = 20) -> str:
    from ..db.database import db_manager
    from ..db.repository import CardOperationRepository
    async with db_manager.session() as session:
        repo = CardOperationRepository(session)
        ops = await repo.query(user_id=user_id, action=action, limit=limit)
    records = []
    for op in ops:
        records.append({
            "action": op.action,
            "user_name": op.user_name,
            "assignee_name": op.assignee_name,
            "record_id": op.record_id,
            "result": op.result,
            "created_at": op.created_at.isoformat() if op.created_at else "",
            "error_message": op.error_message or "",
        })
    return json.dumps({"operations": records, "total": len(records)}, ensure_ascii=False)


@register_tool("update_daily_progress")
async def _handle_update_daily_progress(progress_id: int, status: str, note: str = "") -> str:
    from ..db.database import db_manager
    from ..db.repository import DailyProgressRepository
    async with db_manager.session() as session:
        repo = DailyProgressRepository(session)
        dp = await repo.update_progress(progress_id, status, note=note)
        if not dp:
            return json.dumps({"error": "进展记录不存在"}, ensure_ascii=False)
        if status == "completed" and dp.task_record_id:
            try:
                bitable = _require_dependencies().bitable
                await bitable.update_record(dp.task_record_id, {"状态": "已完成"})
            except Exception as e:
                logger.warning("bitable_status_update_failed", error=str(e))
        remaining = await repo.get_pending(dp.user_id, dp.date)
        all_done = all(p.status != "pending" for p in remaining)
    result = {"success": True, "task": dp.task_title, "status": status}
    if all_done:
        result["all_tasks_updated"] = True
        result["encouragement"] = "所有任务都已更新，请鼓励用户"
    return json.dumps(result, ensure_ascii=False)


@register_tool("propose_bitable_update")
async def _handle_propose_bitable_update(
    record_id: str, fields: dict, context: dict,
    title: str = "", table_id: str = "",
) -> str:
    deps = _require_dependencies()
    user_id = context.get("user_id", "")
    chat_id = context.get("chat_id", "")
    chat_type = context.get("chat_type", "p2p")

    if not user_id and not chat_id:
        return json.dumps({"error": "缺少用户上下文，无法发送确认卡片"}, ensure_ascii=False)

    # Store fields in Redis instead of embedding in card value (SEC-103)
    pending_data = {
        "record_id": record_id,
        "fields": fields,
        "proposer_id": user_id,
    }
    if table_id:
        pending_data["table_id"] = table_id
    action_id = await _store_pending_op(pending_data)

    # Build field summary for the card
    field_lines = _format_fields_display(fields)

    card = deps.card_renderer.build_bitable_update_confirmation(
        title=title,
        record_id=record_id,
        field_lines=field_lines,
        action_id=action_id,
        is_group_chat=chat_type == "group",
    )

    card_content = json.dumps(card, ensure_ascii=False)

    if chat_type == "p2p":
        await deps.messenger.send_message(
            receive_id=user_id, receive_id_type="open_id",
            msg_type="interactive", content=card_content,
        )
    else:
        await deps.messenger.send_message(
            receive_id=chat_id, receive_id_type="chat_id",
            msg_type="interactive", content=card_content,
        )

    await record_op(
        user_id=user_id,
        user_name=context.get("user_name", ""),
        action="propose_update",
        table_id=table_id,
        record_id=record_id,
        fields=fields,
    )

    return json.dumps({
        "success": True,
        "card_sent": True,
    }, ensure_ascii=False)


@register_tool("propose_bitable_create")
async def _handle_propose_bitable_create(fields: dict, context: dict, table_id: str = "") -> str:
    deps = _require_dependencies()
    user_id = context.get("user_id", "")
    chat_id = context.get("chat_id", "")
    chat_type = context.get("chat_type", "p2p")

    if not user_id and not chat_id:
        return json.dumps({"error": "缺少用户上下文，无法发送确认卡片"}, ensure_ascii=False)

    # Store fields in Redis instead of embedding in card value (SEC-103)
    pending_data = {
        "fields": fields,
        "proposer_id": user_id,
    }
    if table_id:
        pending_data["table_id"] = table_id
    action_id = await _store_pending_op(pending_data)

    field_lines = _format_fields_display(fields)

    card = deps.card_renderer.build_bitable_create_confirmation(
        field_lines=field_lines,
        action_id=action_id,
        is_group_chat=chat_type == "group",
    )

    card_content = json.dumps(card, ensure_ascii=False)

    if chat_type == "p2p":
        await deps.messenger.send_message(
            receive_id=user_id, receive_id_type="open_id",
            msg_type="interactive", content=card_content,
        )
    else:
        await deps.messenger.send_message(
            receive_id=chat_id, receive_id_type="chat_id",
            msg_type="interactive", content=card_content,
        )

    await record_op(
        user_id=user_id,
        user_name=context.get("user_name", ""),
        action="propose_create",
        table_id=table_id,
        fields=fields,
    )

    return json.dumps({
        "success": True,
        "card_sent": True,
    }, ensure_ascii=False)


@register_tool("sync_now")
async def _handle_sync_now() -> str:
    from shared.infra.event_bus import event_bus
    from shared.schemas.event import Event, EventTypes

    await event_bus.connect()
    event = Event.create(
        event_type=EventTypes.SYNC_TRIGGER,
        source_agent="chat-agent",
        payload={"triggered_by": "chat_tool"},
    )
    ok = await event_bus.publish(event)
    if ok:
        return json.dumps({"success": True, "message": "同步任务已触发"}, ensure_ascii=False)
    return json.dumps({"error": "同步触发失败"}, ensure_ascii=False)


@register_tool("search_feishu_user")
async def _handle_search_feishu_user(query: str, context: dict | None = None) -> str:
    # SEC-004: require authenticated user
    context = context or {}
    if not context.get("user_id"):
        return json.dumps(
            {"error": "权限不足：需要认证用户才能搜索飞书用户"},
            ensure_ascii=False,
        )

    is_email = "@" in query
    is_mobile = query.isdigit() and len(query) == 11

    emails = [query] if is_email else []
    mobiles = [query] if is_mobile else []

    if not emails and not mobiles:
        return json.dumps({"users": [], "message": "请提供邮箱或11位手机号"}, ensure_ascii=False)

    users = await _require_dependencies().contact_lookup.lookup_user_ids(
        emails=emails,
        mobiles=mobiles,
    )
    return json.dumps(
        {
            "users": [
                {"user_id": user["user_id"], "name": user.get("name", query)}
                for user in users
                if user.get("user_id")
            ],
            "total": len(users),
        },
        ensure_ascii=False,
    )


@register_tool("send_feishu_message")
async def _handle_send_feishu_message(
    user_id: str, message: str, context: dict | None = None,
) -> str:
    # SEC-004: require authenticated user
    context = context or {}
    caller_id = context.get("user_id")
    if not caller_id:
        return json.dumps(
            {"error": "权限不足：需要认证用户才能发送飞书消息"},
            ensure_ascii=False,
        )

    # SEC-004: non-admin users can only send messages to themselves
    is_admin = context.get("is_admin", False)
    if not is_admin and caller_id != user_id:
        return json.dumps(
            {"error": "权限不足：非管理员只能给自己发送消息"},
            ensure_ascii=False,
        )

    messenger = _require_dependencies().messenger
    await messenger.send_message(
        receive_id=user_id,
        receive_id_type="open_id",
        msg_type="text",
        content=json.dumps({"text": message}),
    )
    return json.dumps({"success": True, "message": "消息已发送"}, ensure_ascii=False)
