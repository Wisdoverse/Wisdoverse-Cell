"""Tests for BitableService — feishu multi-dimensional table operations."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.integrations.feishu import bitable as _bitable_mod
from shared.integrations.feishu.bitable import BitableService, get_bitable_service

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_record(record_id: str, fields: dict | None = None) -> MagicMock:
    """Create a mock bitable record object."""
    rec = MagicMock()
    rec.record_id = record_id
    rec.fields = fields or {"name": f"record_{record_id}"}
    return rec


def _make_table(table_id: str, name: str) -> MagicMock:
    """Create a mock bitable table object."""
    tbl = MagicMock()
    tbl.table_id = table_id
    tbl.name = name
    return tbl


@pytest.fixture
def mock_sdk():
    """Mock the lark_oapi SDK on a BitableService instance."""
    sdk = MagicMock()
    return sdk


@pytest.fixture
def service(mock_sdk):
    """BitableService with patched _sdk property and settings."""
    with patch.object(_bitable_mod, "settings") as mock_settings:
        mock_settings.feishu_bitable_app_token = "app_token_test"
        mock_settings.feishu_bitable_table_id = "tbl_test"
        svc = BitableService()

    # Patch _sdk property to return our mock
    type(svc)._sdk = property(lambda self: mock_sdk)
    return svc


# ──────────────────────────────────────────────
# TestListTables
# ──────────────────────────────────────────────


class TestListTables:
    """Tests for BitableService.list_tables."""

    @pytest.mark.asyncio
    async def test_list_tables__success__returns_table_list(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.items = [
            _make_table("tbl_001", "Members"),
            _make_table("tbl_002", "Tasks"),
        ]
        mock_sdk.bitable.v1.app_table.alist = AsyncMock(return_value=resp)

        result = await service.list_tables("app_custom")

        assert len(result) == 2
        assert result[0] == {"table_id": "tbl_001", "name": "Members"}
        assert result[1] == {"table_id": "tbl_002", "name": "Tasks"}

    @pytest.mark.asyncio
    async def test_list_tables__failure__raises_exception(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = False
        resp.msg = "permission denied"
        mock_sdk.bitable.v1.app_table.alist = AsyncMock(return_value=resp)

        with pytest.raises(Exception, match="list_tables failed"):
            await service.list_tables()

    @pytest.mark.asyncio
    async def test_list_tables__empty_items__returns_empty_list(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.items = None
        mock_sdk.bitable.v1.app_table.alist = AsyncMock(return_value=resp)

        result = await service.list_tables()

        assert result == []


# ──────────────────────────────────────────────
# TestListRecords
# ──────────────────────────────────────────────


class TestListRecords:
    """Tests for BitableService.list_records."""

    @pytest.mark.asyncio
    async def test_list_records__basic_query__returns_items(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.items = [_make_record("rec_001"), _make_record("rec_002")]
        resp.data.page_token = None
        resp.data.has_more = False
        resp.data.total = 2
        mock_sdk.bitable.v1.app_table_record.alist = AsyncMock(return_value=resp)

        result = await service.list_records()

        assert len(result["items"]) == 2
        assert result["items"][0]["record_id"] == "rec_001"
        assert result["has_more"] is False
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_list_records__with_filter__passes_filter_to_builder(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.items = []
        resp.data.page_token = None
        resp.data.has_more = False
        resp.data.total = 0
        mock_sdk.bitable.v1.app_table_record.alist = AsyncMock(return_value=resp)

        result = await service.list_records(filter_expr='Status="Active"')

        assert result["items"] == []
        assert result["total"] == 0
        mock_sdk.bitable.v1.app_table_record.alist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_records__with_page_token__returns_pagination_info(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.items = [_make_record("rec_010")]
        resp.data.page_token = "pt_next_page"
        resp.data.has_more = True
        resp.data.total = 50
        mock_sdk.bitable.v1.app_table_record.alist = AsyncMock(return_value=resp)

        result = await service.list_records(page_token="pt_current")

        assert result["page_token"] == "pt_next_page"
        assert result["has_more"] is True
        assert result["total"] == 50

    @pytest.mark.asyncio
    async def test_list_records__failure__raises_exception(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = False
        resp.msg = "table not found"
        mock_sdk.bitable.v1.app_table_record.alist = AsyncMock(return_value=resp)

        with pytest.raises(Exception, match="list_records failed"):
            await service.list_records()


# ──────────────────────────────────────────────
# TestCreateRecord
# ──────────────────────────────────────────────


class TestCreateRecord:
    """Tests for BitableService.create_record."""

    @pytest.mark.asyncio
    async def test_create_record__success__returns_record_id(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.record.record_id = "rec_new_001"
        mock_sdk.bitable.v1.app_table_record.acreate = AsyncMock(return_value=resp)

        with patch.object(_bitable_mod, "AppTableRecord", create=True):
            record_id = await service.create_record({"name": "New Item"})

        assert record_id == "rec_new_001"

    @pytest.mark.asyncio
    async def test_create_record__failure__raises_exception(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = False
        resp.msg = "invalid fields"
        mock_sdk.bitable.v1.app_table_record.acreate = AsyncMock(return_value=resp)

        with patch.object(_bitable_mod, "AppTableRecord", create=True):
            with pytest.raises(Exception, match="create_record failed"):
                await service.create_record({"name": "Bad"})


# ──────────────────────────────────────────────
# TestUpdateRecord
# ──────────────────────────────────────────────


class TestUpdateRecord:
    """Tests for BitableService.update_record."""

    @pytest.mark.asyncio
    async def test_update_record__success__returns_true(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = True
        mock_sdk.bitable.v1.app_table_record.aupdate = AsyncMock(return_value=resp)

        with patch.object(_bitable_mod, "AppTableRecord", create=True):
            result = await service.update_record("rec_001", {"status": "done"})

        assert result is True

    @pytest.mark.asyncio
    async def test_update_record__failure__raises_exception(self, service, mock_sdk):
        resp = MagicMock()
        resp.success.return_value = False
        resp.msg = "record not found"
        mock_sdk.bitable.v1.app_table_record.aupdate = AsyncMock(return_value=resp)

        with patch.object(_bitable_mod, "AppTableRecord", create=True):
            with pytest.raises(Exception, match="update_record failed"):
                await service.update_record("rec_missing", {"status": "done"})


# ──────────────────────────────────────────────
# TestListAllRecords
# ──────────────────────────────────────────────


class TestListAllRecords:
    """Tests for BitableService.list_all_records (pagination loop)."""

    @pytest.mark.asyncio
    async def test_list_all_records__single_page__returns_all(self, service):
        service.list_records = AsyncMock(return_value={
            "items": [{"record_id": "rec_1", "fields": {}}],
            "has_more": False,
            "page_token": None,
        })

        result = await service.list_all_records()

        assert len(result) == 1
        assert result[0]["record_id"] == "rec_1"
        service.list_records.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_all_records__multi_page__iterates_until_done(self, service):
        service.list_records = AsyncMock(side_effect=[
            {
                "items": [{"record_id": "rec_1", "fields": {}}],
                "has_more": True,
                "page_token": "pt_page2",
            },
            {
                "items": [{"record_id": "rec_2", "fields": {}}],
                "has_more": True,
                "page_token": "pt_page3",
            },
            {
                "items": [{"record_id": "rec_3", "fields": {}}],
                "has_more": False,
                "page_token": None,
            },
        ])

        result = await service.list_all_records()

        assert len(result) == 3
        assert [r["record_id"] for r in result] == ["rec_1", "rec_2", "rec_3"]
        assert service.list_records.await_count == 3

    @pytest.mark.asyncio
    async def test_list_all_records__empty__returns_empty_list(self, service):
        service.list_records = AsyncMock(return_value={
            "items": [],
            "has_more": False,
            "page_token": None,
        })

        result = await service.list_all_records()

        assert result == []


# ──────────────────────────────────────────────
# TestBitableServiceSingleton
# ──────────────────────────────────────────────


class TestBitableServiceSingleton:
    """Tests for get_bitable_service singleton."""

    def test_get_bitable_service__returns_same_instance(self):
        """Module-level _bitable_service is a constant; get_bitable_service returns it."""
        svc1 = get_bitable_service()
        svc2 = get_bitable_service()

        assert svc1 is svc2
        assert isinstance(svc1, BitableService)

    def test_get_bitable_service__returns_module_level_instance(self):
        """get_bitable_service returns the same object as the module attribute."""
        import shared.integrations.feishu.bitable as mod

        assert get_bitable_service() is mod._bitable_service
