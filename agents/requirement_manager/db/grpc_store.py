"""SQLAlchemy adapter for the Requirement Manager gRPC boundary."""

from sqlalchemy import func, or_, select

from ..core.grpc_ports import RequirementGrpcStore
from ..models.requirement import Requirement
from .database import DatabaseManager, db_manager
from .repository import RequirementRepository


class SqlAlchemyRequirementGrpcStore(RequirementGrpcStore):
    """SQLAlchemy-backed store for gRPC requirement reads and fallback writes."""

    def __init__(self, database: DatabaseManager | None = None):
        self._db_manager = database or db_manager

    async def get_many(self, requirement_ids: list[str]) -> list[Requirement]:
        requirements: list[Requirement] = []
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)
            for requirement_id in requirement_ids:
                requirement = await repo.get_by_id(requirement_id)
                if requirement is not None:
                    requirements.append(requirement)
        return requirements

    async def get_by_id(self, requirement_id: str) -> Requirement | None:
        async with self._db_manager.session() as session:
            return await RequirementRepository(session).get_by_id(requirement_id)

    async def list_requirements(
        self,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Requirement], int]:
        skip = (page - 1) * page_size
        async with self._db_manager.session() as session:
            return await RequirementRepository(session).list_all(
                status=status,
                skip=skip,
                limit=page_size,
            )

    async def search_requirements(
        self,
        *,
        keyword: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Requirement], int]:
        keyword_pattern = f"%{keyword}%"
        skip = (page - 1) * page_size
        conditions = or_(
            Requirement.title.ilike(keyword_pattern),
            Requirement.description.ilike(keyword_pattern),
        )

        async with self._db_manager.session() as session:
            total = (
                await session.execute(
                    select(func.count()).select_from(Requirement).where(conditions)
                )
            ).scalar() or 0
            result = await session.execute(
                select(Requirement)
                .where(conditions)
                .order_by(Requirement.created_at.desc())
                .offset(skip)
                .limit(page_size)
            )
            return list(result.scalars().all()), total

    async def confirm(
        self,
        requirement_id: str,
        confirmed_by: str,
    ) -> Requirement | None:
        async with self._db_manager.session() as session:
            return await RequirementRepository(session).confirm(
                requirement_id,
                confirmed_by=confirmed_by,
            )

    async def reject(
        self,
        requirement_id: str,
        *,
        reason: str,
        rejected_by: str,
    ) -> Requirement | None:
        async with self._db_manager.session() as session:
            return await RequirementRepository(session).reject(
                requirement_id,
                reason=reason,
                rejected_by=rejected_by,
            )
