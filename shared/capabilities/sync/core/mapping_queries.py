"""Application query use cases for sync mapping read models."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SyncMappingView:
    """Read model exposed by the sync mapping query use case."""

    id: int
    op_work_package_id: int
    feishu_record_id: str | None
    op_project_id: int | None
    updated_at: datetime | None

    @classmethod
    def from_row(cls, row: object) -> "SyncMappingView":
        return cls(
            id=row.id,
            op_work_package_id=row.op_work_package_id,
            feishu_record_id=row.feishu_record_id,
            op_project_id=row.op_project_id,
            updated_at=row.updated_at,
        )


class SyncMappingQueryRepository(Protocol):
    async def list_all(self) -> Sequence[object]:
        """Return persisted sync mapping rows."""


class SyncMappingQueryService:
    """Application use case for listing sync mapping read models."""

    def __init__(self, repository: SyncMappingQueryRepository):
        self._repository = repository

    async def list_mappings(self) -> list[SyncMappingView]:
        rows = await self._repository.list_all()
        return [SyncMappingView.from_row(row) for row in rows]
