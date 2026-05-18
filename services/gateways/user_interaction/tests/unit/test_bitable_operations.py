from unittest.mock import AsyncMock

import pytest

from services.gateways.user_interaction.core.bitable_operations import (
    BitableConfirmCommand,
    BitableCreateCommand,
    BitableOperationUseCase,
    BitableRejectCommand,
    sanitize_fields,
)
from services.gateways.user_interaction.core.config import UserInteractionCoreConfig
from shared.integrations.feishu.cards.tools import FeishuToolCardRenderer


def test_sanitize_fields_flattens_duplex_record_ids() -> None:
    fields = {"DRI (负责人)": [{"record_ids": ["rec_a"]}, {"record_ids": ["rec_b"]}]}

    assert sanitize_fields(fields)["DRI (负责人)"] == ["rec_a", "rec_b"]


@pytest.mark.asyncio
async def test_resolve_duplex_links_maps_open_ids_to_member_records() -> None:
    bitable = AsyncMock()
    bitable.list_fields = AsyncMock(return_value=[{"field_name": "DRI", "type": 20}])
    bitable.list_records = AsyncMock(
        return_value={
            "items": [
                {
                    "record_id": "rec_member",
                    "fields": {"OpenID": [{"id": "ou_1"}]},
                }
            ]
        }
    )
    config = UserInteractionCoreConfig(
        feishu_bitable_app_token="app-token",
        feishu_bitable_table_id="task-table",
        feishu_bitable_member_table_id="member-table",
    )

    result = await BitableOperationUseCase().resolve_duplex_links(
        {"DRI": [{"id": "ou_1"}]},
        "",
        bitable=bitable,
        config=config,
    )

    assert result == {"DRI": ["rec_member"]}
    bitable.list_fields.assert_awaited_once_with(
        app_token="app-token",
        table_id="task-table",
    )
    bitable.list_records.assert_awaited_once_with(
        app_token="app-token",
        table_id="member-table",
        page_size=100,
    )


@pytest.mark.asyncio
async def test_confirm_update_uses_pending_operation_and_returns_log_command() -> None:
    bitable = AsyncMock()
    bitable.update_record = AsyncMock(return_value=True)
    pending_lookup = AsyncMock(
        return_value={
            "record_id": "rec_pending",
            "fields": {"状态": "已完成"},
            "table_id": "task-table",
        }
    )

    result = await BitableOperationUseCase().confirm_update(
        BitableConfirmCommand(action_id="act_1", user_id="ou_1", user_name="Alice"),
        bitable=bitable,
        pending_lookup=pending_lookup,
        renderer=FeishuToolCardRenderer(),
        config=UserInteractionCoreConfig(),
    )

    bitable.update_record.assert_awaited_once_with(
        "rec_pending",
        {"状态": "已完成"},
        table_id="task-table",
    )
    assert result.operation_log is not None
    assert result.operation_log.action == "confirm_update"
    assert result.operation_log.result == "success"
    assert result.operation_log.record_id == "rec_pending"


@pytest.mark.asyncio
async def test_create_record_returns_failure_card_and_log_command() -> None:
    bitable = AsyncMock()
    bitable.create_record = AsyncMock(side_effect=RuntimeError("API timeout"))

    result = await BitableOperationUseCase().create_record(
        BitableCreateCommand(fields={"任务": "测试"}, user_id="ou_1"),
        bitable=bitable,
        pending_lookup=AsyncMock(),
        renderer=FeishuToolCardRenderer(),
        config=UserInteractionCoreConfig(),
    )

    assert result.operation_log is not None
    assert result.operation_log.action == "confirm_create"
    assert result.operation_log.result == "failed"
    assert result.operation_log.error_message == "API timeout"
    assert "失败" in result.card["header"]["title"]["content"]


@pytest.mark.asyncio
async def test_reject_operation_records_denial_and_log_command() -> None:
    denial_tracker = AsyncMock()
    denial_tracker.record_denial = AsyncMock()

    result = await BitableOperationUseCase().reject_operation(
        BitableRejectCommand(
            action_type="update",
            user_id="ou_1",
            user_name="Alice",
            fields={"状态": "已完成"},
            table_id="task-table",
            record_id="rec_1",
        ),
        renderer=FeishuToolCardRenderer(),
        denial_tracker=denial_tracker,
    )

    denial_tracker.record_denial.assert_awaited_once_with(
        agent_id="chat-agent",
        user_id="ou_1",
        action_type="update",
        table_id="task-table",
        reason="user_rejected",
    )
    assert result.denial_error == ""
    assert result.operation_log is not None
    assert result.operation_log.action == "reject_update"
    assert result.operation_log.result == "rejected"
    assert result.operation_log.record_id == "rec_1"
    assert result.card["header"]["title"]["content"]


@pytest.mark.asyncio
async def test_reject_operation_surfaces_denial_tracking_failure() -> None:
    denial_tracker = AsyncMock()
    denial_tracker.record_denial = AsyncMock(side_effect=RuntimeError("redis down"))

    result = await BitableOperationUseCase().reject_operation(
        BitableRejectCommand(action_type="create", user_id="ou_1"),
        renderer=FeishuToolCardRenderer(),
        denial_tracker=denial_tracker,
    )

    assert result.denial_error == "redis down"
    assert result.operation_log is not None
    assert result.operation_log.action == "reject_create"
    assert result.operation_log.result == "rejected"
