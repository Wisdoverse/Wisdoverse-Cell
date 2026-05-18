"""Application query use cases for daily progress read models."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DailyProgressView:
    """Read model exposed by the daily progress query use case."""

    id: int
    user_id: str
    user_name: str
    date: date
    task_record_id: str
    task_title: str
    status: str
    note: str
    raw_reply: str

    @classmethod
    def from_row(cls, row: object) -> "DailyProgressView":
        return cls(
            id=row.id,
            user_id=row.user_id,
            user_name=row.user_name,
            date=row.date,
            task_record_id=row.task_record_id,
            task_title=row.task_title,
            status=row.status,
            note=row.note or "",
            raw_reply=row.raw_reply or "",
        )

    def to_response_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "date": self.date.isoformat(),
            "task_record_id": self.task_record_id,
            "task_title": self.task_title,
            "status": self.status,
            "note": self.note,
            "raw_reply": self.raw_reply,
        }


class DailyProgressQueryRepository(Protocol):
    async def get_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str = "",
    ) -> Sequence[object]:
        """Return persisted daily progress rows in the requested date range."""


class DailyProgressQueryService:
    """Application use case for listing daily progress read models."""

    def __init__(self, repository: DailyProgressQueryRepository):
        self._repository = repository

    async def list_progress(
        self,
        *,
        target_date: date | None,
        user_id: str = "",
        days: int = 1,
    ) -> list[DailyProgressView]:
        end = target_date or date.today()
        start = end - timedelta(days=max(days, 1) - 1)
        rows = await self._repository.get_by_date_range(start, end, user_id=user_id)
        return [DailyProgressView.from_row(row) for row in rows]

    async def list_progress_response(
        self,
        *,
        target_date: date | None,
        user_id: str = "",
        days: int = 1,
    ) -> dict[str, object]:
        entries = await self.list_progress(
            target_date=target_date,
            user_id=user_id,
            days=days,
        )
        results = [entry.to_response_dict() for entry in entries]
        return {"entries": results, "total": len(results)}
