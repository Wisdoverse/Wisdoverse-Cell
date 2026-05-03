"""Unit tests for daily task Bitable config wiring."""

from unittest.mock import AsyncMock

import pytest

from services.gateways.user_interaction.core.config import UserInteractionCoreConfig
from services.gateways.user_interaction.core.daily_tasks import (
    DailyTaskDependencies,
    _get_members,
    _get_user_tasks,
    configure_daily_task_dependencies,
)


@pytest.fixture(autouse=True)
def reset_daily_task_dependencies():
    configure_daily_task_dependencies(None)
    yield
    configure_daily_task_dependencies(None)


def configure_with_bitable(bitable):
    configure_daily_task_dependencies(
        DailyTaskDependencies(
            bitable=bitable,
            messenger=AsyncMock(),
            config=UserInteractionCoreConfig.from_values(
                feishu_bitable_app_token="app-token",
                feishu_bitable_member_table_id="member-table",
                feishu_bitable_table_id="task-table",
            ),
        )
    )


@pytest.mark.asyncio
async def test_get_members_uses_injected_member_table_config() -> None:
    bitable = AsyncMock()
    bitable.list_records = AsyncMock(
        return_value={
            "items": [
                {
                    "record_id": "rec_member_1",
                    "fields": {
                        "Member": [{"id": "ou_user_1", "name": "Alice"}],
                    },
                }
            ]
        }
    )
    configure_with_bitable(bitable)

    members = await _get_members()

    assert members == [
        {"open_id": "ou_user_1", "name": "Alice", "record_id": "rec_member_1"}
    ]
    bitable.list_records.assert_awaited_once_with(
        app_token="app-token",
        table_id="member-table",
        page_size=100,
    )


@pytest.mark.asyncio
async def test_get_user_tasks_uses_injected_task_table_config() -> None:
    bitable = AsyncMock()
    bitable.list_records = AsyncMock(
        return_value={
            "items": [
                {
                    "record_id": "rec_task_1",
                    "fields": {
                        "状态": "进行中",
                        "DRI (负责人)": [{"record_ids": ["rec_member_1"]}],
                        "任务(动宾短语)": "Build report",
                        "优先级": "High",
                        "计划完成日期": "2026-05-04",
                    },
                },
                {
                    "record_id": "rec_task_2",
                    "fields": {
                        "状态": "已完成(Done)",
                        "DRI (负责人)": [{"record_ids": ["rec_member_1"]}],
                        "任务(动宾短语)": "Ignore done task",
                    },
                },
            ]
        }
    )
    configure_with_bitable(bitable)

    tasks = await _get_user_tasks("rec_member_1")

    assert tasks == [
        {
            "record_id": "rec_task_1",
            "title": "Build report",
            "priority": "High",
            "status": "进行中",
            "due_date": "2026-05-04",
        }
    ]
    bitable.list_records.assert_awaited_once_with(
        app_token="app-token",
        table_id="task-table",
        page_size=50,
    )
