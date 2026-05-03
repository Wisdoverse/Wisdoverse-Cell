"""
Unit Tests - Bitable API (_sanitize_fields & async timeout fallback)

Tests for field sanitization logic used before writing to Feishu bitable,
and for graceful handling when bitable operations are slow.
"""
from unittest.mock import AsyncMock, patch

import pytest

from services.gateways.user_interaction.api.bitable import (
    ConfirmRequest,
    CreateRequest,
    _sanitize_fields,
    confirm_update,
    create_record,
)

# ---------------------------------------------------------------------------
# Duplex Link format
# ---------------------------------------------------------------------------

def test_sanitize_fields_duplex_link_extracts_record_ids():
    """Duplex link format [{"record_ids": ["recXXX"]}] should be flattened."""
    fields = {
        "DRI (负责人)": [{"record_ids": ["rec_abc"], "table_id": "tbl_1"}],
    }
    result = _sanitize_fields(fields)
    assert result["DRI (负责人)"] == ["rec_abc"]


def test_sanitize_fields_duplex_link_multiple_records():
    """Multiple duplex link items should have all record_ids merged."""
    fields = {
        "关联成员": [
            {"record_ids": ["rec_a", "rec_b"]},
            {"record_ids": ["rec_c"]},
        ],
    }
    result = _sanitize_fields(fields)
    assert result["关联成员"] == ["rec_a", "rec_b", "rec_c"]


# ---------------------------------------------------------------------------
# None values
# ---------------------------------------------------------------------------

def test_sanitize_fields_skips_none_values():
    """None values should be removed from the output."""
    fields = {
        "任务(动宾短语)": "写文档",
        "优先级": None,
        "状态": "待办",
    }
    result = _sanitize_fields(fields)
    assert "优先级" not in result
    assert result["任务(动宾短语)"] == "写文档"
    assert result["状态"] == "待办"


# ---------------------------------------------------------------------------
# String-to-number conversion safety
# ---------------------------------------------------------------------------

def test_sanitize_fields_does_not_convert_strings_to_numbers():
    """Strings that look numeric must NOT be blindly converted to numbers."""
    fields = {
        "任务(动宾短语)": "123号任务",
        "状态": "42",
        "备注": "3.14",
    }
    result = _sanitize_fields(fields)
    # All values should remain as strings
    assert result["任务(动宾短语)"] == "123号任务"
    assert result["状态"] == "42"
    assert result["备注"] == "3.14"


# ---------------------------------------------------------------------------
# Passthrough for normal values
# ---------------------------------------------------------------------------

def test_sanitize_fields_passes_through_normal_values():
    """Normal scalar values should pass through unchanged."""
    fields = {
        "任务(动宾短语)": "编写测试",
        "状态": "待办",
        "优先级": "Normal",
        "计划完成日期": 1709251200000,
    }
    result = _sanitize_fields(fields)
    assert result == fields


def test_sanitize_fields_person_field_passthrough():
    """Person field with ou_ prefix should be normalized to [{"id": ...}] format."""
    fields = {
        "DRI (负责人)": [{"id": "ou_user1", "name": "Alice", "extra": True}],
    }
    result = _sanitize_fields(fields)
    assert result["DRI (负责人)"] == [{"id": "ou_user1"}]


def test_sanitize_fields_empty_dict():
    """Empty input should return empty output."""
    assert _sanitize_fields({}) == {}


# ---------------------------------------------------------------------------
# Async endpoint: confirm_update error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_update_returns_error_card_on_failure():
    """When bitable update raises, a failure card should be returned (not an exception)."""
    with patch("services.gateways.user_interaction.api.bitable.bitable_service") as mock_svc, \
         patch("services.gateways.user_interaction.api.bitable._resolve_duplex_links", new_callable=AsyncMock, side_effect=lambda f, **kw: f), \
         patch("services.gateways.user_interaction.api.bitable.record_op", new_callable=AsyncMock):
        mock_svc.update_record = AsyncMock(side_effect=Exception("API timeout"))

        req = ConfirmRequest(record_id="rec_test", fields={"状态": "已完成"})
        result = await confirm_update(req)

        assert isinstance(result, dict)
        assert "header" in result
        # Should be a failure card, not a success
        title = result["header"]["title"]
        assert "失败" in title.get("content", "")


@pytest.mark.asyncio
async def test_create_record_returns_error_card_on_failure():
    """When bitable create raises, a failure card should be returned."""
    with patch("services.gateways.user_interaction.api.bitable.bitable_service") as mock_svc, \
         patch("services.gateways.user_interaction.api.bitable._resolve_duplex_links", new_callable=AsyncMock, side_effect=lambda f, **kw: f), \
         patch("services.gateways.user_interaction.api.bitable.record_op", new_callable=AsyncMock):
        mock_svc.create_record = AsyncMock(side_effect=Exception("API timeout"))

        req = CreateRequest(fields={"任务": "测试任务"})
        result = await create_record(req)

        assert isinstance(result, dict)
        assert "header" in result
        title = result["header"]["title"]
        assert "失败" in title.get("content", "")


@pytest.mark.asyncio
async def test_confirm_update_success_returns_success_card():
    """Successful update should return a green success card."""
    with patch("services.gateways.user_interaction.api.bitable.bitable_service") as mock_svc, \
         patch("services.gateways.user_interaction.api.bitable._resolve_duplex_links", new_callable=AsyncMock, side_effect=lambda f, **kw: f), \
         patch("services.gateways.user_interaction.api.bitable.record_op", new_callable=AsyncMock):
        mock_svc.update_record = AsyncMock(return_value=None)

        req = ConfirmRequest(record_id="rec_ok", fields={"状态": "已完成"})
        result = await confirm_update(req)

        assert isinstance(result, dict)
        assert "header" in result
        title = result["header"]["title"]
        assert "更新" in title.get("content", "") or "已" in title.get("content", "")
