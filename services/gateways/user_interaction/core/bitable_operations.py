"""Application use cases for confirmed Bitable card operations."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from shared.core import BitableTablePort

from .card_ports import ToolCardRendererPort
from .config import UserInteractionCoreConfig
from .tools import _format_fields_display

PendingOperationLookup = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class BitableConfirmCommand:
    """Command for confirming a Bitable record update."""

    record_id: str = ""
    fields: dict[str, Any] | None = None
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


@dataclass(frozen=True, slots=True)
class BitableCreateCommand:
    """Command for confirming a Bitable record creation."""

    fields: dict[str, Any] | None = None
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


@dataclass(frozen=True, slots=True)
class BitableRejectCommand:
    """Command for rejecting a proposed Bitable operation."""

    action_type: str = ""
    user_id: str = ""
    user_name: str = ""
    fields: dict[str, Any] | None = None
    table_id: str = ""
    record_id: str = ""


@dataclass(frozen=True, slots=True)
class BitableOperationLogCommand:
    """Operation-log request emitted by a confirmed Bitable operation."""

    user_id: str
    user_name: str
    action: str
    result: str
    table_id: str = ""
    record_id: str = ""
    fields: dict[str, Any] | None = None
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class BitableOperationResult:
    """Use-case result for an HTTP adapter to return and record asynchronously."""

    card: dict[str, Any]
    operation_log: BitableOperationLogCommand | None = None
    denial_error: str = ""


class BitableDenialTrackerPort(Protocol):
    """Denial-tracking operation needed by Bitable rejection use cases."""

    async def record_denial(
        self,
        *,
        agent_id: str,
        user_id: str,
        action_type: str,
        table_id: str = "",
        reason: str = "",
    ) -> None:
        """Record that a user rejected a proposed action."""


def sanitize_fields(fields: dict[str, Any], table_id: str = "") -> dict[str, Any]:
    """Sanitize field values to match Feishu Bitable API requirements."""
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue

        if isinstance(value, list) and value and isinstance(value[0], dict):
            first = value[0]
            if "record_ids" in first:
                all_ids: list[str] = []
                for item in value:
                    ids = item.get("record_ids") or []
                    all_ids.extend(ids)
                if all_ids:
                    cleaned[key] = all_ids
                continue
            if "id" in first and str(first.get("id", "")).startswith("ou_"):
                cleaned[key] = [{"id": item["id"]} for item in value if "id" in item]
                continue

        cleaned[key] = value
    return cleaned


class BitableOperationUseCase:
    """Application boundary for confirmed Bitable write operations."""

    async def resolve_duplex_links(
        self,
        fields: dict[str, Any],
        table_id: str = "",
        *,
        bitable: BitableTablePort,
        config: UserInteractionCoreConfig,
    ) -> dict[str, Any]:
        target_table = table_id or config.feishu_bitable_table_id
        member_table = config.feishu_bitable_member_table_id
        if not member_table:
            return fields

        try:
            field_list = await bitable.list_fields(
                app_token=config.feishu_bitable_app_token,
                table_id=target_table,
            )
        except Exception:
            return fields

        duplex_fields = {
            field["field_name"] for field in field_list if field.get("type") in (20, 21)
        }
        if not duplex_fields:
            return fields

        to_resolve: dict[str, list[str]] = {}
        for key, value in fields.items():
            if key not in duplex_fields:
                continue
            if isinstance(value, list) and value and isinstance(value[0], dict):
                open_ids = [
                    item["id"]
                    for item in value
                    if isinstance(item, dict)
                    and str(item.get("id", "")).startswith("ou_")
                ]
                if open_ids:
                    to_resolve[key] = open_ids

        if not to_resolve:
            return fields

        try:
            all_open_ids = {oid for ids in to_resolve.values() for oid in ids}
            records = await bitable.list_records(
                app_token=config.feishu_bitable_app_token,
                table_id=member_table,
                page_size=100,
            )
            oid_to_rec: dict[str, str] = {}
            for record in records.get("items", []):
                for field_value in record.get("fields", {}).values():
                    if isinstance(field_value, list):
                        for item in field_value:
                            if (
                                isinstance(item, dict)
                                and item.get("id") in all_open_ids
                            ):
                                oid_to_rec[item["id"]] = record["record_id"]
        except Exception:
            return fields

        resolved = dict(fields)
        for key, open_ids in to_resolve.items():
            rec_ids = [oid_to_rec[oid] for oid in open_ids if oid in oid_to_rec]
            if rec_ids:
                resolved[key] = rec_ids
        return resolved

    async def confirm_update(
        self,
        command: BitableConfirmCommand,
        *,
        bitable: BitableTablePort,
        pending_lookup: PendingOperationLookup,
        renderer: ToolCardRendererPort,
        config: UserInteractionCoreConfig,
    ) -> BitableOperationResult:
        record_id = command.record_id
        fields = command.fields or {}
        table_id = command.table_id
        if command.action_id:
            pending = await pending_lookup(command.action_id)
            if not pending:
                return BitableOperationResult(
                    card=renderer.build_bitable_operation_expired(operation="修改")
                )
            record_id = pending.get("record_id", record_id)
            fields = pending.get("fields", fields)
            table_id = pending.get("table_id", table_id)

        try:
            kwargs = {"table_id": table_id} if table_id else {}
            sanitized = sanitize_fields(fields, table_id)
            sanitized = await self.resolve_duplex_links(
                sanitized,
                table_id,
                bitable=bitable,
                config=config,
            )
            await bitable.update_record(record_id, sanitized, **kwargs)
            field_lines = _format_fields_display(fields)
            return BitableOperationResult(
                card=renderer.build_bitable_update_success(
                    record_id=record_id,
                    field_lines=field_lines,
                ),
                operation_log=BitableOperationLogCommand(
                    user_id=command.user_id,
                    user_name=command.user_name,
                    action="confirm_update",
                    result="success",
                    table_id=table_id,
                    record_id=record_id,
                    fields=fields,
                ),
            )
        except Exception as exc:
            return BitableOperationResult(
                card=renderer.build_bitable_update_failure(record_id=record_id),
                operation_log=BitableOperationLogCommand(
                    user_id=command.user_id,
                    user_name=command.user_name,
                    action="confirm_update",
                    result="failed",
                    table_id=table_id,
                    record_id=record_id,
                    fields=fields,
                    error_message=str(exc),
                ),
            )

    async def create_record(
        self,
        command: BitableCreateCommand,
        *,
        bitable: BitableTablePort,
        pending_lookup: PendingOperationLookup,
        renderer: ToolCardRendererPort,
        config: UserInteractionCoreConfig,
    ) -> BitableOperationResult:
        fields = command.fields or {}
        table_id = command.table_id
        if command.action_id:
            pending = await pending_lookup(command.action_id)
            if not pending:
                return BitableOperationResult(
                    card=renderer.build_bitable_operation_expired(operation="创建")
                )
            fields = pending.get("fields", fields)
            table_id = pending.get("table_id", table_id)

        try:
            kwargs = {"table_id": table_id} if table_id else {}
            sanitized = sanitize_fields(fields, table_id)
            sanitized = await self.resolve_duplex_links(
                sanitized,
                table_id,
                bitable=bitable,
                config=config,
            )
            record_id = await bitable.create_record(sanitized, **kwargs)
            field_lines = _format_fields_display(fields)
            return BitableOperationResult(
                card=renderer.build_bitable_create_success(
                    record_id=record_id,
                    field_lines=field_lines,
                ),
                operation_log=BitableOperationLogCommand(
                    user_id=command.user_id,
                    user_name=command.user_name,
                    action="confirm_create",
                    result="success",
                    table_id=table_id,
                    record_id=record_id,
                    fields=fields,
                ),
            )
        except Exception as exc:
            return BitableOperationResult(
                card=renderer.build_bitable_create_failure(),
                operation_log=BitableOperationLogCommand(
                    user_id=command.user_id,
                    user_name=command.user_name,
                    action="confirm_create",
                    result="failed",
                    table_id=table_id,
                    fields=fields,
                    error_message=str(exc),
                ),
            )

    async def reject_operation(
        self,
        command: BitableRejectCommand,
        *,
        renderer: ToolCardRendererPort,
        denial_tracker: BitableDenialTrackerPort | None = None,
    ) -> BitableOperationResult:
        action = f"reject_{command.action_type}" if command.action_type else "reject"
        denial_error = ""
        if command.action_type and command.user_id and denial_tracker is not None:
            try:
                await denial_tracker.record_denial(
                    agent_id="chat-agent",
                    user_id=command.user_id,
                    action_type=command.action_type,
                    table_id=command.table_id or "",
                    reason="user_rejected",
                )
            except Exception as exc:
                denial_error = str(exc)

        return BitableOperationResult(
            card=renderer.build_bitable_rejection(action_type=command.action_type),
            operation_log=BitableOperationLogCommand(
                user_id=command.user_id,
                user_name=command.user_name,
                action=action,
                result="rejected",
                table_id=command.table_id,
                record_id=command.record_id,
                fields=command.fields or {},
            ),
            denial_error=denial_error,
        )
