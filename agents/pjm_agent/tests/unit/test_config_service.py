"""Unit tests for agents.pjm_agent.core.config_service.PMConfigService."""

from unittest.mock import AsyncMock

import pytest

from agents.pjm_agent.core.config import PJMCoreConfig
from agents.pjm_agent.core.config_service import PMConfigService


@pytest.fixture
def mock_bitable():
    b = AsyncMock()
    b.list_all_records = AsyncMock(return_value=[])
    return b


def make_service(
    mock_bitable,
    *,
    app_token: str = "token123",
    member_table_id: str = "",
    project_table_id: str = "",
    rules_table_id: str = "",
) -> PMConfigService:
    return PMConfigService(
        mock_bitable,
        config=PJMCoreConfig.from_values(
            feishu_pm_app_token=app_token,
            feishu_pm_member_table_id=member_table_id,
            feishu_pm_project_table_id=project_table_id,
            feishu_pm_rules_table_id=rules_table_id,
        ),
    )


@pytest.mark.asyncio
async def test_refresh_loads_all_configs(mock_bitable):
    """When tokens and table IDs are set, refresh populates members, projects, and rules."""
    svc = make_service(
        mock_bitable,
        member_table_id="member_table",
        project_table_id="project_table",
        rules_table_id="rules_table",
    )
    member_records = [{"fields": {"name": "Alice", "role": "dev"}}]
    project_records = [{"fields": {"name": "Project X", "status": "active"}}]
    rule_records = [{"fields": {"规则名称": "max_tasks", "规则值": "10"}}]

    async def mock_list_all(app_token, table_id):
        if table_id == "member_table":
            return member_records
        elif table_id == "project_table":
            return project_records
        elif table_id == "rules_table":
            return rule_records
        return []

    mock_bitable.list_all_records = AsyncMock(side_effect=mock_list_all)

    await svc.refresh()

    assert len(svc.members) == 1
    assert svc.members[0]["name"] == "Alice"
    assert len(svc.projects) == 1
    assert svc.projects[0]["name"] == "Project X"
    assert svc.rules == {"max_tasks": "10"}


@pytest.mark.asyncio
async def test_refresh_no_token_skips(mock_bitable):
    """When feishu_pm_app_token is empty, refresh returns early without loading."""
    svc = make_service(mock_bitable, app_token="")

    await svc.refresh()

    assert svc.members == []
    assert svc.projects == []
    assert svc.rules == {}
    mock_bitable.list_all_records.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_partial_failure_keeps_old(mock_bitable):
    """If member fetch fails but project fetch succeeds, members keep old data, projects update."""
    svc = make_service(
        mock_bitable,
        member_table_id="member_table",
        project_table_id="project_table",
    )
    old_members = [{"name": "OldMember"}]
    svc._members = old_members

    call_count = 0

    async def mock_list_all(app_token, table_id):
        nonlocal call_count
        call_count += 1
        if table_id == "member_table":
            raise ConnectionError("Feishu API timeout")
        elif table_id == "project_table":
            return [{"fields": {"name": "NewProject"}}]
        return []

    mock_bitable.list_all_records = AsyncMock(side_effect=mock_list_all)

    await svc.refresh()

    # Members should remain unchanged (old data kept)
    assert svc.members == old_members
    # Projects should be updated
    assert len(svc.projects) == 1
    assert svc.projects[0]["name"] == "NewProject"


def test_get_rule_default(mock_bitable):
    """get_rule returns the default when the key is missing."""
    svc = make_service(mock_bitable)
    assert svc.get_rule("missing", "fallback") == "fallback"


def test_get_rule_exists(mock_bitable):
    """get_rule returns the stored value when the key exists."""
    svc = make_service(mock_bitable)
    svc._rules = {"max_tasks": "10", "notify": "true"}
    assert svc.get_rule("max_tasks") == "10"
    assert svc.get_rule("notify") == "true"
