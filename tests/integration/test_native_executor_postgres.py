"""Real PostgreSQL ownership, replay and interrupted native executor coverage."""

import asyncio
import os
from contextlib import asynccontextmanager
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.app.native_executor import NativeExecutorUseCase, request_digest
from shared.core.native_executor import NativeExecutorError
from shared.infra.native_executor_store import SqlAlchemyNativeExecutorLedger
from shared.protocols.executor import ExecutorRequest, ExecutorResponse

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DATABASE_URL.startswith("postgresql"),
        reason="TEST_DATABASE_URL must provide disposable PostgreSQL",
    ),
]
OWNERS = [
    ("requirement_manager", "ingest"),
    ("pjm_agent", "get_decompose"),
    ("dev_agent", "get_task_status"),
    ("qa_agent", "run"),
]


@asynccontextmanager
async def _ledger(owner):
    schema = "native_executor_test_" + uuid4().hex
    admin = create_async_engine(DATABASE_URL)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    table = import_module(f"agents.{owner}.db.executor_ledger").executor_table
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ledger = SqlAlchemyNativeExecutorLedger(sessions, table)
    try:
        await ledger.initialize()
        yield ledger, sessions, table
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _command(action):
    return ExecutorRequest(
        schema_version="1.0",
        company_id="cmp_native_pg",
        agent_id="delivery-role",
        run_id="run-native-pg",
        action="wakeup",
        input={"action": action},
        max_cost_usd=0.5,
    )


def _use_case(ledger, handler, action):
    return NativeExecutorUseCase(
        ledger,
        handler,
        runtime_id="native-owner",
        company_id="cmp_native_pg",
        allowed_actions=frozenset({action}),
    )


@pytest.mark.parametrize("owner,action", OWNERS)
async def test_postgres_native_executor_competing_claims_and_restart_replay(owner, action):
    async with _ledger(owner) as (ledger, sessions, table):
        entered, release = asyncio.Event(), asyncio.Event()
        effects = []

        async def handler(_):
            effects.append("effect")
            entered.set()
            await release.wait()
            return {"status": "ok", "native_id": "synthetic-result"}

        command = _command(action)
        first = asyncio.create_task(
            _use_case(ledger, handler, action).execute(command, command.run_id)
        )
        try:
            await asyncio.wait_for(entered.wait(), 5)
            # Independent session sees intent before the handler completes.
            fresh = SqlAlchemyNativeExecutorLedger(sessions, table)
            assert (await fresh.lookup(command.company_id, command.run_id)).state == "running"
            with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
                await _use_case(fresh, handler, action).execute(command, command.run_id)
        finally:
            release.set()
            result = await asyncio.wait_for(first, 5)
        assert result.status == "recorded"
        replay = await _use_case(
            SqlAlchemyNativeExecutorLedger(sessions, table), handler, action
        ).execute(command, command.run_id)
        assert replay == result
        assert effects == ["effect"]
        changed = command.model_copy(update={"input": {"action": action, "different": True}})
        with pytest.raises(NativeExecutorError, match="executor_request_conflict"):
            await _use_case(fresh, handler, action).execute(changed, command.run_id)
        assert effects == ["effect"]


@pytest.mark.parametrize("owner,action", OWNERS)
async def test_postgres_native_uncertain_intent_is_not_reclaimed_after_restart(owner, action):
    async with _ledger(owner) as (ledger, sessions, table):
        command = _command(action)
        digest = request_digest(command)
        assert (await ledger.claim(command, digest)).acquired
        await ledger.mark_uncertain(command.run_id, digest)
        effects = []

        async def handler(_):
            effects.append("must-not-run")
            return {}

        fresh = SqlAlchemyNativeExecutorLedger(sessions, table)
        with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
            await _use_case(fresh, handler, action).execute(command, command.run_id)
        assert effects == []
        # A stale completion cannot overwrite an explicitly uncertain owner state.
        with pytest.raises(NativeExecutorError, match="executor_receipt_ownership_changed"):
            await fresh.complete(
                command.run_id,
                digest,
                ExecutorResponse(
                    schema_version="1.0",
                    status="recorded",
                    summary="late",
                    cost_usd=0.5,
                    cost_is_estimate=True,
                ),
            )
        assert (await fresh.lookup(command.company_id, command.run_id)).state == "uncertain"
