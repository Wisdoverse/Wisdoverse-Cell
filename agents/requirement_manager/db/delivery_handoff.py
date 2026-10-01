"""Requirement-owned mapping and atomic outbox adapter."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.schemas.event import Event

from ..core.domain.delivery_handoff import ConfirmedRequirementSnapshot, DeliveryHandoffReceipt
from ..models.base import Base
from ..models.requirement import Requirement
from .repository import RequirementEventOutboxRepository


class RequirementDeliveryHandoffTable(Base):
    __tablename__ = "requirement_delivery_handoffs"
    requirement_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("requirements.id"), primary_key=True
    )
    company_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    wp_id: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    __table_args__ = (
        UniqueConstraint("company_id", "project_id", "wp_id", name="uq_requirement_delivery_wp"),
    )


class SqlAlchemyDeliveryHandoffTransaction:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_requirement(self, requirement_id: str) -> ConfirmedRequirementSnapshot | None:
        row = await self._session.scalar(
            select(Requirement).where(Requirement.id == requirement_id).with_for_update()
        )
        if row is None:
            return None
        return ConfirmedRequirementSnapshot(
            row.id, row.title, row.description, row.status, row.confirmed_by
        )

    async def get_receipt(self, requirement_id: str) -> DeliveryHandoffReceipt | None:
        row = await self._session.get(RequirementDeliveryHandoffTable, requirement_id)
        return None if row is None else DeliveryHandoffReceipt.model_validate(row.receipt)

    async def save(self, receipt: DeliveryHandoffReceipt, event: Event) -> None:
        self._session.add(
            RequirementDeliveryHandoffTable(
                requirement_id=receipt.requirement_id,
                company_id=receipt.company_id,
                project_id=receipt.project_id,
                wp_id=receipt.wp_id,
                receipt=receipt.model_dump(mode="json"),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_requirement_delivery_wp" in str(exc.orig):
                raise ValueError("handoff_work_package_already_mapped") from exc
            raise
        await RequirementEventOutboxRepository(self._session).add(event)


class SqlAlchemyDeliveryHandoffStore:
    def __init__(
        self,
        sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    ) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlAlchemyDeliveryHandoffTransaction]:
        async with self._sessions() as session:
            try:
                yield SqlAlchemyDeliveryHandoffTransaction(session)
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
