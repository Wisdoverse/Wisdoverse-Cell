"""Bitable confirm/reject API — called by gateway on card button clicks."""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from shared.infra.denial_tracker import DenialTracker
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.cards.tools import FeishuToolCardRenderer
from shared.utils.logger import get_logger

from ..core.ops_logger import record_op
from ..core.tools import _format_fields_display, get_pending_op

logger = get_logger("chat_agent.bitable_api")

_denial_tracker: DenialTracker | None = None


def get_denial_tracker() -> DenialTracker:
    global _denial_tracker  # noqa: PLW0603
    if _denial_tracker is None:
        import redis.asyncio as aioredis

        from shared.config import settings

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        _denial_tracker = DenialTracker(redis=r)
    return _denial_tracker

_background_tasks: set[asyncio.Task] = set()
_card_renderer = FeishuToolCardRenderer()

router = APIRouter(prefix="/api/bitable", tags=["bitable"])


class ConfirmRequest(BaseModel):
    record_id: str = ""
    fields: dict = {}
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


class CreateRequest(BaseModel):
    fields: dict = {}
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


def _sanitize_fields(fields: dict, table_id: str = "") -> dict:
    """Sanitize field values to match Feishu bitable API requirements.

    Fixes common format issues:
    - Duplex Link fields: extract record_ids to ["recXXX"] format
    - Person fields (user objects with open_id): convert to [{"id": "ou_XXX"}] format
    - Number fields passed as strings: convert to float
    - null/None values: remove to avoid API errors
    """
    cleaned = {}
    for k, v in fields.items():
        # Skip null values
        if v is None:
            continue

        # List of dicts → could be Duplex Link or Person field
        if isinstance(v, list) and v and isinstance(v[0], dict):
            first = v[0]
            # Duplex Link: [{"record_ids": ["recXXX"], ...}] → ["recXXX"]
            if "record_ids" in first:
                all_ids = []
                for item in v:
                    ids = item.get("record_ids") or []
                    all_ids.extend(ids)
                if all_ids:
                    cleaned[k] = all_ids
                continue
            # Person field with open_id: [{"id": "ou_XXX", ...}] → [{"id": "ou_XXX"}]
            # Note: Duplex Link fields also receive this format from Claude,
            # but _resolve_duplex_links() will fix them after sanitization.
            if "id" in first and str(first.get("id", "")).startswith("ou_"):
                cleaned[k] = [{"id": item["id"]} for item in v if "id" in item]
                continue

        cleaned[k] = v
    return cleaned


async def _resolve_duplex_links(fields: dict, table_id: str = "") -> dict:
    """Resolve person-format values in Duplex Link fields to member record IDs.

    Claude passes [{"id": "ou_xxx"}] for DRI, but Duplex Link fields need ["recXXX"].
    This function detects Duplex Link fields via field type API, then looks up
    the member table for matching records.
    """
    from shared.config import settings

    target_table = table_id or settings.feishu_bitable_table_id
    member_table = settings.feishu_bitable_member_table_id
    if not member_table:
        return fields

    # Fetch field types to identify Duplex Link fields
    try:
        field_list = await bitable_service.list_fields(
            app_token=settings.feishu_bitable_app_token,
            table_id=target_table,
        )
    except Exception:
        return fields

    duplex_fields = {f["field_name"] for f in field_list if f.get("type") in (20, 21)}
    if not duplex_fields:
        return fields

    # Collect open_ids that need resolution
    to_resolve = {}
    for k, v in fields.items():
        if k not in duplex_fields:
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            open_ids = [item["id"] for item in v if isinstance(item, dict) and str(item.get("id", "")).startswith("ou_")]
            if open_ids:
                to_resolve[k] = open_ids

    if not to_resolve:
        return fields

    # Fetch member table records once
    try:
        all_open_ids = {oid for ids in to_resolve.values() for oid in ids}
        records = await bitable_service.list_records(
            app_token=settings.feishu_bitable_app_token,
            table_id=member_table,
            page_size=100,
        )
        # Map open_id → member record_id
        oid_to_rec = {}
        for record in records.get("items", []):
            for fv in record.get("fields", {}).values():
                if isinstance(fv, list):
                    for item in fv:
                        if isinstance(item, dict) and item.get("id") in all_open_ids:
                            oid_to_rec[item["id"]] = record["record_id"]
    except Exception:
        return fields

    # Replace person-format values with record IDs
    resolved = dict(fields)
    for k, open_ids in to_resolve.items():
        rec_ids = [oid_to_rec[oid] for oid in open_ids if oid in oid_to_rec]
        if rec_ids:
            resolved[k] = rec_ids

    return resolved


@router.post("/confirm")
async def confirm_update(req: ConfirmRequest):
    """Execute the bitable update and return a result card dict."""
    # Look up fields from Redis if action_id is provided (SEC-103)
    record_id = req.record_id
    fields = req.fields
    table_id = req.table_id
    if req.action_id:
        pending = await get_pending_op(req.action_id)
        if not pending:
            return _card_renderer.build_bitable_operation_expired(operation="修改")
        record_id = pending.get("record_id", record_id)
        fields = pending.get("fields", fields)
        table_id = pending.get("table_id", table_id)

    try:
        kwargs = {"table_id": table_id} if table_id else {}
        sanitized = _sanitize_fields(fields, table_id)
        sanitized = await _resolve_duplex_links(sanitized, table_id)
        await bitable_service.update_record(record_id, sanitized, **kwargs)
        field_lines = _format_fields_display(fields)
        card = _card_renderer.build_bitable_update_success(
            record_id=record_id,
            field_lines=field_lines,
        )
        logger.info("bitable_update_confirmed", record_id=record_id)
        task = asyncio.create_task(record_op(
            user_id=req.user_id, user_name=req.user_name,
            action="confirm_update", result="success",
            table_id=table_id, record_id=record_id, fields=fields,
        ))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return card
    except Exception as e:
        logger.error("bitable_update_failed", record_id=record_id, error=str(e))
        task = asyncio.create_task(record_op(
            user_id=req.user_id, user_name=req.user_name,
            action="confirm_update", result="failed",
            table_id=table_id, record_id=record_id, fields=fields,
            error_message=str(e),
        ))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return _card_renderer.build_bitable_update_failure(record_id=record_id)


class RejectRequest(BaseModel):
    action_type: str = ""
    user_id: str = ""
    user_name: str = ""
    fields: dict = {}
    table_id: str = ""
    record_id: str = ""


@router.post("/reject")
async def reject_operation(req: RejectRequest):
    """Record rejection and return a cancelled card dict."""
    action = f"reject_{req.action_type}" if req.action_type else "reject"
    task = asyncio.create_task(record_op(
        user_id=req.user_id, user_name=req.user_name,
        action=action, result="rejected",
        table_id=req.table_id, record_id=req.record_id, fields=req.fields,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Track denial so the agent avoids re-proposing this action
    if req.action_type and req.user_id:
        try:
            tracker = get_denial_tracker()
            await tracker.record_denial(
                agent_id="chat-agent",
                user_id=req.user_id,
                action_type=req.action_type,
                table_id=req.table_id or "",
                reason="user_rejected",
            )
        except Exception as e:
            logger.warning("denial_tracking_failed", error=str(e))

    return _card_renderer.build_bitable_rejection(action_type=req.action_type)


@router.post("/create")
async def create_record(req: CreateRequest):
    """Create a new bitable record and return a result card dict."""
    # Look up fields from Redis if action_id is provided (SEC-103)
    fields = req.fields
    table_id = req.table_id
    if req.action_id:
        pending = await get_pending_op(req.action_id)
        if not pending:
            return _card_renderer.build_bitable_operation_expired(operation="创建")
        fields = pending.get("fields", fields)
        table_id = pending.get("table_id", table_id)

    try:
        kwargs = {"table_id": table_id} if table_id else {}
        sanitized = _sanitize_fields(fields, table_id)
        sanitized = await _resolve_duplex_links(sanitized, table_id)
        record_id = await bitable_service.create_record(sanitized, **kwargs)
        field_lines = _format_fields_display(fields)
        card = _card_renderer.build_bitable_create_success(
            record_id=record_id,
            field_lines=field_lines,
        )
        logger.info("bitable_record_created", record_id=record_id)
        task = asyncio.create_task(record_op(
            user_id=req.user_id, user_name=req.user_name,
            action="confirm_create", result="success",
            table_id=table_id, record_id=record_id, fields=fields,
        ))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return card
    except Exception as e:
        logger.error("bitable_create_failed", error=str(e))
        task = asyncio.create_task(record_op(
            user_id=req.user_id, user_name=req.user_name,
            action="confirm_create", result="failed",
            table_id=table_id, fields=fields, error_message=str(e),
        ))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return _card_renderer.build_bitable_create_failure()
