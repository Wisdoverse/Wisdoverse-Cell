"""SQL ledger adapter, instantiated only with an owning runtime's table/session."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, MetaData, RowMapping, String, Table, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.native_executor import ExecutorClaim, NativeExecutorError
from shared.protocols.executor import ExecutorRequest, ExecutorResponse

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def executor_ledger_table(name: str) -> Table:
    """Build portable receipt storage in a separate, owner-local metadata registry."""
    return Table(
        name,
        MetaData(),
        Column("run_id", String(48), primary_key=True),
        Column("company_id", String(48), nullable=False),
        Column("request_hash", String(64), nullable=False),
        Column("state", String(16), nullable=False),
        Column("response", JSON, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )


class SqlAlchemyNativeExecutorLedger:
    def __init__(self, sessions: SessionProvider, table: Table) -> None:
        self._sessions = sessions
        self._table = table

    async def initialize(self) -> None:
        """Development-only DDL; deployed schemas must be migrated explicitly."""
        async with self._sessions() as session:
            connection = await session.connection()
            await connection.run_sync(self._table.metadata.create_all)
            await session.commit()

    async def verify_schema(self) -> None:
        """Fail startup before effects if the deployed receipt schema is missing."""
        async with self._sessions() as session:
            await session.execute(select(self._table).limit(0))

    async def claim(self, request: ExecutorRequest, request_hash: str) -> ExecutorClaim:
        async with self._sessions() as session:
            dialect = session.get_bind().dialect.name
            if dialect not in {"postgresql", "sqlite"}:
                raise NativeExecutorError("executor_database_not_supported", 503)
            insert = pg_insert if dialect == "postgresql" else sqlite_insert
            now = datetime.now(UTC)
            inserted = await session.scalar(
                insert(self._table)
                .values(
                    run_id=request.run_id,
                    company_id=request.company_id,
                    request_hash=request_hash,
                    state="running",
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["run_id"])
                .returning(self._table.c.run_id)
            )
            if inserted is not None:
                # Commit before returning permission to perform any business effect.
                await session.commit()
                return ExecutorClaim(True, "running")
            row = (
                (
                    await session.execute(
                        select(self._table).where(self._table.c.run_id == request.run_id)
                    )
                )
                .mappings()
                .one()
            )
            if row["company_id"] != request.company_id or row["request_hash"] != request_hash:
                # A conflicting in-flight intent may still have effects; fail conservatively.
                status = 503 if row["state"] in {"running", "uncertain"} else 409
                raise NativeExecutorError("executor_request_conflict", status)
            return self._claim_from_row(row)

    async def complete(self, run_id: str, request_hash: str, response: ExecutorResponse) -> None:
        async with self._sessions() as session:
            completed = await session.scalar(
                update(self._table)
                .where(
                    self._table.c.run_id == run_id,
                    self._table.c.request_hash == request_hash,
                    self._table.c.state == "running",
                )
                .values(
                    state=response.status,
                    response=response.model_dump(mode="json"),
                    updated_at=datetime.now(UTC),
                )
                .returning(self._table.c.run_id)
            )
            if completed is None:
                raise NativeExecutorError("executor_receipt_ownership_changed", 503)
            await session.commit()

    async def mark_uncertain(self, run_id: str, request_hash: str) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(self._table)
                .where(
                    self._table.c.run_id == run_id,
                    self._table.c.request_hash == request_hash,
                    self._table.c.state == "running",
                )
                .values(state="uncertain", updated_at=datetime.now(UTC))
            )
            await session.commit()

    async def lookup(self, company_id: str, run_id: str) -> ExecutorClaim | None:
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        select(self._table).where(
                            self._table.c.run_id == run_id, self._table.c.company_id == company_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            return None if row is None else self._claim_from_row(row)

    @staticmethod
    def _claim_from_row(row: RowMapping) -> ExecutorClaim:
        response = (
            ExecutorResponse.model_validate(row["response"])
            if row["response"] is not None
            else None
        )
        return ExecutorClaim(False, row["state"], response)
