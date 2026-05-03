"""
BitableService - Feishu Bitable operation service.

Provides Bitable CRUD operations through the lark-oapi SDK.
"""
from typing import Any

from lark_oapi.api.bitable.v1 import (
    CreateAppTableFieldRequest,
    CreateAppTableRecordRequest,
    ListAppTableFieldRequest,
    ListAppTableRecordRequest,
    ListAppTableRequest,
    UpdateAppTableRecordRequest,
)

from shared.config import settings
from shared.utils.logger import get_logger

from .client import get_feishu_client

logger = get_logger("feishu.bitable")


class BitableService:
    """Feishu Bitable service."""

    def __init__(self):
        self.app_token = settings.feishu_bitable_app_token
        self.table_id = settings.feishu_bitable_table_id

    @property
    def _sdk(self):
        return get_feishu_client()._sdk

    async def list_tables(self, app_token: str | None = None) -> list[dict]:
        """List all tables in a Bitable app."""
        token = app_token or self.app_token
        req = ListAppTableRequest.builder().app_token(token).build()
        resp = await self._sdk.bitable.v1.app_table.alist(req)
        if not resp.success():
            raise Exception(f"list_tables failed: {resp.msg}")
        return [
            {"table_id": t.table_id, "name": t.name}
            for t in (resp.data.items or [])
        ]

    async def list_records(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        """Query Bitable records."""
        token = app_token or self.app_token
        tid = table_id or self.table_id

        builder = (
            ListAppTableRecordRequest.builder()
            .app_token(token)
            .table_id(tid)
            .page_size(page_size)
        )
        if page_token:
            builder.page_token(page_token)
        if filter_expr:
            builder.filter(filter_expr)

        resp = await self._sdk.bitable.v1.app_table_record.alist(builder.build())
        if not resp.success():
            raise Exception(f"list_records failed: {resp.msg}")

        items = []
        for record in resp.data.items or []:
            items.append({
                "record_id": record.record_id,
                "fields": record.fields,
            })

        return {
            "items": items,
            "page_token": resp.data.page_token,
            "has_more": resp.data.has_more,
            "total": resp.data.total,
        }

    async def create_record(
        self,
        fields: dict[str, Any],
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> str:
        """Create a record and return its record_id."""
        token = app_token or self.app_token
        tid = table_id or self.table_id

        from lark_oapi.api.bitable.v1 import AppTableRecord

        req = (
            CreateAppTableRecordRequest.builder()
            .app_token(token)
            .table_id(tid)
            .request_body(AppTableRecord.builder().fields(fields).build())
            .build()
        )
        resp = await self._sdk.bitable.v1.app_table_record.acreate(req)
        if not resp.success():
            raise Exception(f"create_record failed: {resp.msg}")
        return resp.data.record.record_id

    async def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> bool:
        """Update a record."""
        token = app_token or self.app_token
        tid = table_id or self.table_id

        from lark_oapi.api.bitable.v1 import AppTableRecord

        req = (
            UpdateAppTableRecordRequest.builder()
            .app_token(token)
            .table_id(tid)
            .record_id(record_id)
            .request_body(AppTableRecord.builder().fields(fields).build())
            .build()
        )
        resp = await self._sdk.bitable.v1.app_table_record.aupdate(req)
        if not resp.success():
            raise Exception(f"update_record failed: {resp.msg}")
        return True

    async def list_all_records(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        filter_expr: str | None = None,
    ) -> list[dict]:
        """Fetch all records across pages."""
        all_items = []
        page_token = None
        while True:
            result = await self.list_records(
                app_token=app_token,
                table_id=table_id,
                page_size=100,
                page_token=page_token,
                filter_expr=filter_expr,
            )
            all_items.extend(result.get("items", []))
            if not result.get("has_more"):
                break
            page_token = result.get("page_token")
        return all_items

    async def list_fields(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> list[dict]:
        """List all fields for a table."""
        token = app_token or self.app_token
        tid = table_id or self.table_id
        req = (
            ListAppTableFieldRequest.builder()
            .app_token(token)
            .table_id(tid)
            .build()
        )
        resp = await self._sdk.bitable.v1.app_table_field.alist(req)
        if not resp.success():
            raise Exception(f"list_fields failed: {resp.msg}")
        return [
            {"field_id": f.field_id, "field_name": f.field_name, "type": f.type}
            for f in (resp.data.items or [])
        ]

    async def create_field(
        self,
        field_name: str,
        field_type: int = 1,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> dict:
        """Create a field. Types: 1=text, 2=number, 3=single-select, 4=multi-select, 5=date, 7=checkbox, 11=user, 15=url."""
        token = app_token or self.app_token
        tid = table_id or self.table_id

        from lark_oapi.api.bitable.v1 import AppTableField

        req = (
            CreateAppTableFieldRequest.builder()
            .app_token(token)
            .table_id(tid)
            .request_body(
                AppTableField.builder()
                .field_name(field_name)
                .type(field_type)
                .build()
            )
            .build()
        )
        resp = await self._sdk.bitable.v1.app_table_field.acreate(req)
        if not resp.success():
            raise Exception(f"create_field failed: {resp.msg}")
        return {
            "field_id": resp.data.field.field_id,
            "field_name": resp.data.field.field_name,
            "type": resp.data.field.type,
        }


def get_bitable_service() -> BitableService:
    """Return the BitableService singleton."""
    return _bitable_service


_bitable_service = BitableService()
bitable_service = _bitable_service
