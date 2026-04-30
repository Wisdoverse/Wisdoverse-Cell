"""Tool definitions for Claude Tool Calling"""
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.config import settings
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.openproject.client import get_op_client
from shared.utils.logger import get_logger

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

# Claude Tool Calling 工具定义
TOOLS = [
    {
        "name": "get_work_packages",
        "description": (
            "获取 OpenProject 中的工作包（公司战略方向级任务，"
            "Epic/Feature）。仅在需要了解大方向时使用，"
            "日常任务查询请优先用 list_bitable_records"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "项目ID"},
                "limit": {"type": "integer", "description": "返回数量限制", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_work_package_detail",
        "description": "获取单个工作包的详细信息",
        "input_schema": {
            "type": "object",
            "properties": {"work_package_id": {"type": "integer", "description": "工作包ID"}},
            "required": ["work_package_id"],
        },
    },
    {
        "name": "update_work_package_progress",
        "description": "更新工作包的进度百分比",
        "input_schema": {
            "type": "object",
            "properties": {
                "work_package_id": {"type": "integer", "description": "工作包ID"},
                "progress": {"type": "integer", "description": "进度百分比（0-100）"},
            },
            "required": ["work_package_id", "progress"],
        },
    },
    {
        "name": "list_bitable_records",
        "description": (
            "查询飞书多维表格记录（员工日常任务主表，"
            "OP 任务的原子拆解）。用户问任务时优先调用此工具"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "返回数量", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "list_member_records",
        "description": (
            "查询飞书成员表（团队成员信息：姓名、部门、"
            "关联任务）。用户问团队、成员、谁负责等问题时调用"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "返回数量", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "query_pm_table",
        "description": (
            "查询飞书多维表格中的其他表。"
            "可查询：categories(大类看板，AI汇总)、weekly_report(周报)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "表名：categories(大类看板) / weekly_report(周报)",
                    "enum": ["categories", "weekly_report"],
                },
                "limit": {"type": "integer", "description": "返回数量", "default": 20},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "propose_bitable_update",
        "description": (
            "提议更新飞书多维表格记录。"
            "会发送确认卡片给用户，用户点击确认后才会执行更新。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "记录ID"},
                "fields": {"type": "object", "description": "要更新的字段"},
                "table_id": {
                    "type": "string",
                    "description": "表ID（来自查询结果，非任务主表时必填）",
                },
            },
            "required": ["record_id", "fields"],
        },
    },
    {
        "name": "propose_bitable_create",
        "description": (
            "提议在飞书多维表格中新建记录。会发送确认卡片，"
            "用户确认后才创建。任务主表字段名：任务(动宾短语)、"
            "状态、DRI (负责人)、优先级、计划完成日期、"
            "所属大类、阻塞原因"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "新记录字段",
                },
                "table_id": {"type": "string", "description": "表ID（不填则默认为任务主表）"},
            },
            "required": ["fields"],
        },
    },
    {
        "name": "add_bitable_field",
        "description": (
            "给飞书多维表格添加新字段（列）。"
            "字段类型：1=文本,2=数字,3=单选,4=多选,"
            "5=日期,7=复选框,11=人员,15=超链接"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field_name": {"type": "string", "description": "字段名称"},
                "field_type": {
                    "type": "integer",
                    "description": "字段类型（默认1=文本）",
                    "default": 1,
                },
                "table_id": {"type": "string", "description": "表ID（不填则默认为任务主表）"},
            },
            "required": ["field_name"],
        },
    },
    {
        "name": "list_bitable_fields",
        "description": "列出飞书多维表格的所有字段（列名和类型）",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "表ID（不填则默认为任务主表）"},
            },
            "required": [],
        },
    },
    {
        "name": "sync_now",
        "description": "立即执行一次同步",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_card_operations",
        "description": (
            "查询卡片操作记录（审计日志）。"
            "可查本周创建了多少任务、谁取消最多、某人最近的操作等"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "按用户过滤（open_id）"},
                "action": {
                    "type": "string",
                    "description": "按操作类型过滤",
                    "enum": ["propose_create", "confirm_create", "reject_create",
                             "propose_update", "confirm_update", "reject_update"],
                },
                "limit": {"type": "integer", "description": "返回数量", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "update_daily_progress",
        "description": "更新员工的每日任务进展。解析员工回复后逐条调用此工具更新。",
        "input_schema": {
            "type": "object",
            "properties": {
                "progress_id": {"type": "integer", "description": "进展记录 ID"},
                "status": {
                    "type": "string",
                    "description": "任务状态",
                    "enum": ["completed", "in_progress", "blocked"],
                },
                "note": {"type": "string", "description": "进展备注"},
            },
            "required": ["progress_id", "status"],
        },
    },
    {
        "name": "search_feishu_user",
        "description": "搜索飞书用户，支持邮箱或11位手机号",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            "required": ["query"],
        },
    },
    {
        "name": "send_feishu_message",
        "description": "发送飞书消息给指定用户",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户的 open_id"},
                "message": {"type": "string", "description": "消息内容"},
            },
            "required": ["user_id", "message"],
        },
    },
]


# Tool registry
_tool_registry: dict[str, Callable] = {}

# Tools that always need context forwarded
_context_tools = {
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
    op = get_op_client()
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
    op = get_op_client()
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
    op = get_op_client()
    await op.update_work_package(work_package_id, {"percentageDone": progress})
    return json.dumps({"success": True, "message": f"进度已更新为 {progress}%"}, ensure_ascii=False)


@register_tool("list_bitable_records")
async def _handle_list_bitable_records(limit: int = 20) -> str:
    from shared.config import settings as _settings
    result = await bitable_service.list_records(page_size=limit)
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
    result = await bitable_service.list_records(
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
    table_map = {
        "categories": _settings.feishu_bitable_category_table_id,
        "weekly_report": _settings.feishu_bitable_report_table_id,
    }
    table_id = table_map.get(table_name)
    if not table_id:
        return json.dumps({"error": f"未知表名: {table_name}"}, ensure_ascii=False)
    result = await bitable_service.list_records(
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
    field_name: str, field_type: int = 1, table_id: str = "",
) -> str:
    kwargs = {"table_id": table_id} if table_id else {}
    result = await bitable_service.create_field(field_name, field_type, **kwargs)
    return json.dumps({"success": True, **result}, ensure_ascii=False)


@register_tool("list_bitable_fields")
async def _handle_list_bitable_fields(table_id: str = "") -> str:
    kwargs = {"table_id": table_id} if table_id else {}
    fields = await bitable_service.list_fields(**kwargs)
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
                await bitable_service.update_record(dp.task_record_id, {"状态": "已完成"})
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
    from shared.integrations.feishu.cards.builder import CardBuilder, truncate_card_if_needed
    from shared.integrations.feishu.client import get_feishu_client

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

    action_value = {
        "action": "confirm_bitable_update",
        "action_id": action_id,
    }

    builder = (
        CardBuilder()
        .set_header("📝 表格修改确认", template="orange")
        .add_markdown(f"**{title or record_id}**\n\n**修改内容**:\n{field_lines}")
        .add_divider()
        .add_action_buttons([
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✓ 确认修改"},
                "type": "primary",
                "value": action_value,
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✗ 取消"},
                "type": "danger",
                "value": {
                    "action": "reject_bitable_update",
                },
            },
        ])
    )
    if chat_type == "group":
        builder.add_note("仅提议人可操作此卡片")
    builder.add_note("点击按钮确认或取消此修改")
    card = builder.build()
    card = truncate_card_if_needed(card)

    client = get_feishu_client()
    card_content = json.dumps(card, ensure_ascii=False)

    if chat_type == "p2p":
        await client.send_message(
            receive_id=user_id, receive_id_type="open_id",
            msg_type="interactive", content=card_content,
        )
    else:
        await client.send_message(
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
    from shared.integrations.feishu.cards.builder import CardBuilder, truncate_card_if_needed
    from shared.integrations.feishu.client import get_feishu_client

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

    action_value = {
        "action": "confirm_bitable_create",
        "action_id": action_id,
    }

    builder = (
        CardBuilder()
        .set_header("📋 新建任务确认", template="blue")
        .add_markdown(f"**新任务内容**:\n{field_lines}")
        .add_divider()
        .add_action_buttons([
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✓ 确认创建"},
                "type": "primary",
                "value": action_value,
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✗ 取消"},
                "type": "danger",
                "value": {
                    "action": "reject_bitable_create",
                },
            },
        ])
    )
    if chat_type == "group":
        builder.add_note("仅提议人可操作此卡片")
    builder.add_note("点击按钮确认或取消创建")
    card = builder.build()
    card = truncate_card_if_needed(card)

    client = get_feishu_client()
    card_content = json.dumps(card, ensure_ascii=False)

    if chat_type == "p2p":
        await client.send_message(
            receive_id=user_id, receive_id_type="open_id",
            msg_type="interactive", content=card_content,
        )
    else:
        await client.send_message(
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
    import asyncio

    from lark_oapi.api.contact.v3 import BatchGetIdUserRequest, BatchGetIdUserRequestBody

    from shared.integrations.feishu.client import get_feishu_client

    # SEC-004: require authenticated user
    context = context or {}
    if not context.get("user_id"):
        return json.dumps(
            {"error": "权限不足：需要认证用户才能搜索飞书用户"},
            ensure_ascii=False,
        )

    client = get_feishu_client()
    is_email = "@" in query
    is_mobile = query.isdigit() and len(query) == 11

    emails = [query] if is_email else []
    mobiles = [query] if is_mobile else []

    if not emails and not mobiles:
        return json.dumps({"users": [], "message": "请提供邮箱或11位手机号"}, ensure_ascii=False)

    req = BatchGetIdUserRequest.builder().user_id_type("open_id").request_body(
        BatchGetIdUserRequestBody.builder().emails(emails).mobiles(mobiles).include_resigned(False).build()
    ).build()

    # Lark SDK batch_get_id is synchronous — run in thread to avoid blocking event loop
    resp = await asyncio.to_thread(client._sdk.contact.v3.user.batch_get_id, req)

    if resp.success() and resp.data:
        users = [
            {"user_id": u.user_id, "name": query}
            for u in (resp.data.user_list or [])
            if u.user_id
        ]
        return json.dumps({"users": users, "total": len(users)}, ensure_ascii=False)
    return json.dumps({"users": [], "total": 0}, ensure_ascii=False)


@register_tool("send_feishu_message")
async def _handle_send_feishu_message(
    user_id: str, message: str, context: dict | None = None,
) -> str:
    from shared.integrations.feishu.client import get_feishu_client

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

    client = get_feishu_client()
    await client.send_message(receive_id=user_id, receive_id_type="open_id", msg_type="text",
                              content=json.dumps({"text": message}))
    return json.dumps({"success": True, "message": "消息已发送"}, ensure_ascii=False)
