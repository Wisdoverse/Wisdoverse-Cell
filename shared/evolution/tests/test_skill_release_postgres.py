"""PostgreSQL-only concurrency and compare-and-swap release coverage."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.evolution.db.release_store import (
    SkillReleaseError,
    SqlAlchemySkillReleaseStore,
)
from shared.evolution.db.release_tables import (
    EvolutionSkillRelease,
    EvolutionSkillReleaseCommand,
)
from shared.evolution.db.tables import EvolutionExperiment, EvolutionSkillConfig, evolution_metadata
from shared.evolution.release_contract import SkillReleaseCommand, skill_config_hash


@asynccontextmanager
async def _postgres_schema_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL release tests")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL must use PostgreSQL for release concurrency coverage")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    schema = f"test_skill_release_{uuid4().hex}"
    root_engine = create_async_engine(url)
    async with root_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(evolution_metadata.create_all)
        yield async_sessionmaker(scoped_engine, expire_on_commit=False)
    finally:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(evolution_metadata.drop_all)
        async with root_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


def _skill(version: int, status: str, prompt: str) -> EvolutionSkillConfig:
    return EvolutionSkillConfig(
        skill_id="release-concurrency-skill",
        version=str(version),
        status=status,
        system_prompt=prompt,
        parameters={"temperature": 0},
        few_shot_examples=[],
        output_format="json",
        target_model="model-a",
    )


def _command(
    baseline: EvolutionSkillConfig,
    candidate: EvolutionSkillConfig,
    **updates: object,
) -> SkillReleaseCommand:
    command = SkillReleaseCommand(
        command_id=f"cmd-{uuid4().hex}",
        deployment_id=f"deploy-{uuid4().hex}",
        company_id=settings.control_plane_company_id,
        proposal_id="proposal-postgres-concurrency",
        evaluation_report_id="evaluation-postgres-concurrency",
        evaluation_hash="a" * 64,
        skill_id=baseline.skill_id,
        agent_id="agent-release-test",
        baseline_version=int(baseline.version),
        candidate_version=int(candidate.version),
        baseline_config_hash=skill_config_hash(baseline),
        candidate_config_hash=skill_config_hash(candidate),
        action="shadow",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return command.model_copy(update=updates)


async def _seed_skills(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[EvolutionSkillConfig, EvolutionSkillConfig]:
    baseline = _skill(1, "active", "baseline")
    candidate = _skill(2, "candidate", "candidate")
    async with factory() as session:
        session.add_all([baseline, candidate])
        await session.commit()
    return baseline, candidate


@pytest.mark.asyncio
async def test_postgres_concurrent_replay_writes_one_release_and_command() -> None:
    async with _postgres_schema_factory() as factory:
        baseline, candidate = await _seed_skills(factory)
        command = _command(baseline, candidate)

        async def apply_same_command() -> dict[str, object]:
            async with factory() as session:
                result = await SqlAlchemySkillReleaseStore(session).apply(command)
                await session.commit()
                return result

        first, second = await asyncio.gather(apply_same_command(), apply_same_command())
        assert first == second

        async with factory() as session:
            release_count = await session.scalar(
                select(func.count()).select_from(EvolutionSkillRelease)
            )
            command_count = await session.scalar(
                select(func.count()).select_from(EvolutionSkillReleaseCommand)
            )
            persisted = await SqlAlchemySkillReleaseStore(session).get_command(command.command_id)
        assert release_count == command_count == 1
        assert persisted is not None
        assert persisted["response"] == first


@pytest.mark.asyncio
async def test_postgres_different_deployments_cannot_open_two_skill_canaries() -> None:
    async with _postgres_schema_factory() as factory:
        baseline, candidate = await _seed_skills(factory)
        commands = [
            _command(
                baseline,
                candidate,
                deployment_id=f"deploy-{uuid4().hex}",
            )
            for _ in range(2)
        ]
        for command in commands:
            async with factory() as session:
                await SqlAlchemySkillReleaseStore(session).apply(command)
                await session.commit()

        async def open_canary(command: SkillReleaseCommand) -> str:
            async with factory() as session:
                try:
                    await SqlAlchemySkillReleaseStore(session).apply(
                        command.model_copy(
                            update={
                                "command_id": f"cmd-{uuid4().hex}",
                                "action": "canary",
                                "approval_id": f"approval-{uuid4().hex}",
                            }
                        )
                    )
                    await session.commit()
                    return "canary"
                except SkillReleaseError:
                    await session.rollback()
                    return "blocked"

        outcomes = await asyncio.gather(*(open_canary(command) for command in commands))
        assert sorted(outcomes) == ["blocked", "canary"]

        async with factory() as session:
            canary_count = await session.scalar(
                select(func.count())
                .select_from(EvolutionSkillRelease)
                .where(EvolutionSkillRelease.state == "canary")
            )
        assert canary_count == 1


@pytest.mark.asyncio
async def test_postgres_expired_inflight_command_is_fenced_by_locked_receipt_lookup() -> None:
    async with _postgres_schema_factory() as factory:
        baseline, candidate = await _seed_skills(factory)
        expires_at = datetime.now(UTC) + timedelta(seconds=3)
        expired_command = _command(baseline, candidate, expires_at=expires_at)
        holder = factory()
        apply_session = factory()
        lookup_session = factory()
        apply_task: asyncio.Task[str] | None = None
        lookup_task: asyncio.Task[dict[str, object] | None] | None = None
        try:
            await holder.execute(
                select(EvolutionSkillConfig)
                .where(
                    EvolutionSkillConfig.skill_id == expired_command.skill_id,
                    EvolutionSkillConfig.version.in_(
                        (
                            str(expired_command.baseline_version),
                            str(expired_command.candidate_version),
                        )
                    ),
                )
                .order_by(EvolutionSkillConfig.id)
                .with_for_update()
            )
            apply_pid = await apply_session.scalar(text("SELECT pg_backend_pid()"))
            assert apply_pid is not None

            async def apply_expired() -> str:
                try:
                    await SqlAlchemySkillReleaseStore(apply_session).apply(expired_command)
                except SkillReleaseError as exc:
                    await apply_session.rollback()
                    return str(exc)
                await apply_session.commit()
                return "committed"

            apply_task = asyncio.create_task(apply_expired())
            loop = asyncio.get_running_loop()
            lock_deadline = loop.time() + 2
            waiting_on_lock = False
            while loop.time() < lock_deadline:
                async with factory() as observer:
                    waiting_on_lock = bool(
                        await observer.scalar(
                            text(
                                "SELECT wait_event_type = 'Lock' "
                                "FROM pg_stat_activity WHERE pid = :pid"
                            ),
                            {"pid": apply_pid},
                        )
                    )
                if waiting_on_lock:
                    break
                await asyncio.sleep(0.01)
            assert waiting_on_lock, "command should be waiting on the held skill locks"

            delay = (expires_at - datetime.now(UTC)).total_seconds() + 0.02
            assert 0 < delay < 4
            await asyncio.sleep(delay)
            lookup_task = asyncio.create_task(
                SqlAlchemySkillReleaseStore(lookup_session).get_command(
                    expired_command.command_id,
                    skill_id=expired_command.skill_id,
                    baseline_version=expired_command.baseline_version,
                    candidate_version=expired_command.candidate_version,
                )
            )
            await asyncio.sleep(0.05)
            assert not lookup_task.done(), "receipt lookup must wait on the same skill locks"
        finally:
            await holder.rollback()
            if apply_task is not None:
                await asyncio.gather(apply_task, return_exceptions=True)
            if lookup_task is not None:
                await asyncio.gather(lookup_task, return_exceptions=True)
            await apply_session.close()
            await lookup_session.close()
            await holder.close()

        assert apply_task is not None and lookup_task is not None
        assert await apply_task == "evolution_command_expired"
        assert await lookup_task is None

        fresh_command = _command(
            baseline,
            candidate,
            deployment_id=expired_command.deployment_id,
        )
        async with factory() as session:
            result = await SqlAlchemySkillReleaseStore(session).apply(fresh_command)
            await session.commit()
            old_receipt = await SqlAlchemySkillReleaseStore(session).get_command(
                expired_command.command_id,
                skill_id=expired_command.skill_id,
                baseline_version=expired_command.baseline_version,
                candidate_version=expired_command.candidate_version,
            )
            new_receipt = await SqlAlchemySkillReleaseStore(session).get_command(
                fresh_command.command_id,
                skill_id=fresh_command.skill_id,
                baseline_version=fresh_command.baseline_version,
                candidate_version=fresh_command.candidate_version,
            )
        assert result["state"] == "shadow"
        assert old_receipt is None
        assert new_receipt is not None


@pytest.mark.asyncio
async def test_postgres_rollback_cas_preserves_a_later_active_version() -> None:
    async with _postgres_schema_factory() as factory:
        baseline, candidate = await _seed_skills(factory)
        command = _command(baseline, candidate)
        async with factory() as session:
            store = SqlAlchemySkillReleaseStore(session)
            await store.apply(command)
            await store.apply(
                command.model_copy(
                    update={
                        "command_id": f"cmd-{uuid4().hex}",
                        "action": "canary",
                        "approval_id": "approval-postgres-canary",
                    }
                )
            )
            experiment = (
                await session.execute(
                    select(EvolutionExperiment).where(
                        EvolutionExperiment.experiment_id == command.deployment_id
                    )
                )
            ).scalar_one_or_none()
            assert experiment is not None
            experiment.control_results = [0.8] * 50
            experiment.candidate_results = [0.9] * 50
            await store.apply(
                command.model_copy(
                    update={
                        "command_id": f"cmd-{uuid4().hex}",
                        "action": "promote",
                        "approval_id": "approval-postgres-promote",
                    }
                )
            )
            await session.commit()

        async with factory() as session:
            later_active = _skill(3, "active", "later release")
            candidate_row = (
                await session.execute(
                    select(EvolutionSkillConfig).where(
                        EvolutionSkillConfig.skill_id == command.skill_id,
                        EvolutionSkillConfig.version == str(command.candidate_version),
                    )
                )
            ).scalar_one()
            candidate_row.status = "retired"
            session.add(later_active)
            await session.commit()

        rollback = command.model_copy(
            update={
                "command_id": f"cmd-{uuid4().hex}",
                "action": "rollback",
                "approval_id": "approval-postgres-rollback",
            }
        )
        async with factory() as session:
            with pytest.raises(SkillReleaseError, match="compare_and_swap_failed"):
                await SqlAlchemySkillReleaseStore(session).apply(rollback)
            await session.rollback()

        async with factory() as session:
            baseline_row = (
                await session.execute(
                    select(EvolutionSkillConfig).where(
                        EvolutionSkillConfig.skill_id == command.skill_id,
                        EvolutionSkillConfig.version == str(command.baseline_version),
                    )
                )
            ).scalar_one()
            candidate_row = (
                await session.execute(
                    select(EvolutionSkillConfig).where(
                        EvolutionSkillConfig.skill_id == command.skill_id,
                        EvolutionSkillConfig.version == str(command.candidate_version),
                    )
                )
            ).scalar_one()
            later_row = (
                await session.execute(
                    select(EvolutionSkillConfig).where(
                        EvolutionSkillConfig.skill_id == command.skill_id,
                        EvolutionSkillConfig.version == "3",
                    )
                )
            ).scalar_one()
            release = await session.get(EvolutionSkillRelease, command.deployment_id)

        assert baseline_row.status == "retired"
        assert candidate_row.status == "retired"
        assert later_row.status == "active"
        assert release is not None and release.state == "active"
