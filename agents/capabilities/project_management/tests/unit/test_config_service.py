"""Unit tests for agents.capabilities.project_management.core.config_service.PMConfigService."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_bitable():
    b = AsyncMock()
    b.list_all_records = AsyncMock(return_value=[])
    return b


@pytest.fixture
def svc(mock_bitable):
    from agents.capabilities.project_management.core.config_service import PMConfigService

    return PMConfigService(mock_bitable)


@pytest.mark.asyncio
async def test_refresh_loads_all_configs(svc, mock_bitable):
    """When tokens and table IDs are set, refresh populates members, projects, and rules."""
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

    with patch("agents.capabilities.project_management.core.config_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token123"
        mock_settings.feishu_pm_member_table_id = "member_table"
        mock_settings.feishu_pm_project_table_id = "project_table"
        mock_settings.feishu_pm_rules_table_id = "rules_table"

        await svc.refresh()

    assert len(svc.members) == 1
    assert svc.members[0]["name"] == "Alice"
    assert len(svc.projects) == 1
    assert svc.projects[0]["name"] == "Project X"
    assert svc.rules == {"max_tasks": "10"}


@pytest.mark.asyncio
async def test_refresh_no_token_skips(svc, mock_bitable):
    """When feishu_pm_app_token is empty, refresh returns early without loading."""
    with patch("agents.capabilities.project_management.core.config_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = ""

        await svc.refresh()

    assert svc.members == []
    assert svc.projects == []
    assert svc.rules == {}
    mock_bitable.list_all_records.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_partial_failure_keeps_old(svc, mock_bitable):
    """If member fetch fails but project fetch succeeds, members keep old data, projects update."""
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

    with patch("agents.capabilities.project_management.core.config_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token123"
        mock_settings.feishu_pm_member_table_id = "member_table"
        mock_settings.feishu_pm_project_table_id = "project_table"
        mock_settings.feishu_pm_rules_table_id = ""

        await svc.refresh()

    # Members should remain unchanged (old data kept)
    assert svc.members == old_members
    # Projects should be updated
    assert len(svc.projects) == 1
    assert svc.projects[0]["name"] == "NewProject"


def test_get_rule_default(svc):
    """get_rule returns the default when the key is missing."""
    assert svc.get_rule("missing", "fallback") == "fallback"


def test_get_rule_exists(svc):
    """get_rule returns the stored value when the key exists."""
    svc._rules = {"max_tasks": "10", "notify": "true"}
    assert svc.get_rule("max_tasks") == "10"
    assert svc.get_rule("notify") == "true"
