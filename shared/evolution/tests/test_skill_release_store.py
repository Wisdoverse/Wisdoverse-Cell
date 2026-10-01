from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.evolution.db.release_store import (
    ReleaseCommandConflict,
    ReleaseOwnershipError,
    SqlAlchemySkillReleaseStore,
)
from shared.evolution.db.release_tables import EvolutionSkillRelease
from shared.evolution.db.tables import EvolutionExperiment, EvolutionSkillConfig
from shared.evolution.release_contract import (
    SkillReleaseCommand,
    canonical_hash,
    sign_command,
    skill_config_hash,
    verify_command,
)


def _skill(version: int, status: str, prompt: str) -> EvolutionSkillConfig:
    return EvolutionSkillConfig(
        skill_id="skill-a",
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
    **updates: Any,
) -> SkillReleaseCommand:
    command = SkillReleaseCommand(
        command_id="cmd-1",
        deployment_id="deploy-1",
        company_id=settings.control_plane_company_id,
        proposal_id="proposal-1",
        evaluation_report_id="eval-1",
        evaluation_hash="a" * 64,
        skill_id="skill-a",
        agent_id="agent-a",
        baseline_version=1,
        candidate_version=2,
        baseline_config_hash=skill_config_hash(baseline),
        candidate_config_hash=skill_config_hash(candidate),
        action="shadow",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return command.model_copy(update=updates)


async def _seed(session: AsyncSession) -> tuple[EvolutionSkillConfig, EvolutionSkillConfig]:
    baseline = _skill(1, "active", "baseline")
    candidate = _skill(2, "candidate", "candidate")
    session.add_all([baseline, candidate])
    await session.flush()
    return baseline, candidate


@pytest.mark.asyncio
async def test_atomic_shadow_canary_promote_rollback_and_replay(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    shadow = _command(baseline, candidate)
    first = await store.apply(shadow)
    assert first["state"] == "shadow"
    assert (await store.apply(shadow)) == first
    with pytest.raises(ReleaseCommandConflict):
        await store.apply(shadow.model_copy(update={"action": "canary"}))

    canary = shadow.model_copy(
        update={"command_id": "cmd-2", "action": "canary", "approval_id": "approval-1"}
    )
    assert (await store.apply(canary))["state"] == "canary"
    experiment = (
        await db_session.execute(
            select(EvolutionExperiment).where(EvolutionExperiment.experiment_id == "deploy-1")
        )
    ).scalar_one_or_none()
    assert experiment is not None
    assert (experiment.traffic_pct, experiment.min_samples) == (10, 50)
    experiment.control_results = [0.8] * 50
    experiment.candidate_results = [0.9] * 50
    await db_session.flush()

    promote = shadow.model_copy(
        update={"command_id": "cmd-3", "action": "promote", "approval_id": "approval-promote"}
    )
    assert (await store.apply(promote))["state"] == "active"
    active_baseline = await db_session.get(EvolutionSkillConfig, baseline.id)
    active_candidate = await db_session.get(EvolutionSkillConfig, candidate.id)
    assert active_baseline is not None and active_baseline.status == "retired"
    assert active_candidate is not None and active_candidate.status == "active"
    assert experiment.status == "promoted"

    rollback = shadow.model_copy(
        update={"command_id": "cmd-4", "action": "rollback", "approval_id": "approval-rollback"}
    )
    assert (await store.apply(rollback))["state"] == "rolled_back"
    restored_baseline = await db_session.get(EvolutionSkillConfig, baseline.id)
    retired_candidate = await db_session.get(EvolutionSkillConfig, candidate.id)
    assert restored_baseline is not None and restored_baseline.status == "active"
    assert retired_candidate is not None and retired_candidate.status == "retired"
    assert experiment.status == "rolled_back"
    persisted = (await db_session.execute(select(EvolutionSkillRelease))).scalar_one()
    assert persisted.version == 4


@pytest.mark.asyncio
async def test_hash_and_company_are_checked_before_writes(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    with pytest.raises(ValueError, match="config_hash_mismatch"):
        await store.apply(_command(baseline, candidate, candidate_config_hash="0" * 64))
    with pytest.raises(ReleaseOwnershipError):
        await store.apply(_command(baseline, candidate, company_id="cmp_other"))
    assert await db_session.get(EvolutionSkillRelease, "deploy-1") is None


def test_signature_and_expiry_are_verified() -> None:
    baseline = _skill(1, "active", "baseline")
    candidate = _skill(2, "candidate", "candidate")
    command = _command(baseline, candidate)
    signature = sign_command(command, "s" * 32)
    verify_command(command, signature, "s" * 32)
    with pytest.raises(ValueError, match="signature_invalid"):
        verify_command(command, "0" * 64, "s" * 32)
    with pytest.raises(ValueError, match="expired"):
        verify_command(
            command.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}),
            signature,
            "s" * 32,
        )
    with pytest.raises(ValueError, match="key_required"):
        sign_command(command, "short")


@pytest.mark.asyncio
async def test_frozen_candidate_snapshot_is_rechecked_after_shadow(
    db_session: AsyncSession,
) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    shadow = _command(baseline, candidate)
    await store.apply(shadow)
    candidate.system_prompt = "changed after shadow"
    await db_session.flush()
    with pytest.raises(ValueError, match="config_hash_mismatch"):
        await store.apply(
            shadow.model_copy(
                update={"command_id": "cmd-2", "action": "canary", "approval_id": "approval-1"}
            )
        )
    release = await db_session.get(EvolutionSkillRelease, "deploy-1")
    assert release is not None and release.state == "shadow"


@pytest.mark.asyncio
async def test_rollback_cannot_undo_a_later_active_release(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    shadow = _command(baseline, candidate)
    await store.apply(shadow)
    await store.apply(
        shadow.model_copy(
            update={"command_id": "cmd-2", "action": "canary", "approval_id": "approval-1"}
        )
    )
    experiment = (
        await db_session.execute(
            select(EvolutionExperiment).where(EvolutionExperiment.experiment_id == "deploy-1")
        )
    ).scalar_one_or_none()
    assert experiment is not None
    experiment.control_results = [0.8] * 50
    experiment.candidate_results = [0.9] * 50
    await store.apply(
        shadow.model_copy(
            update={"command_id": "cmd-3", "action": "promote", "approval_id": "approval-promote"}
        )
    )

    # Model a newer release having already made version 3 active.
    candidate.status = "retired"
    newer = _skill(3, "active", "newer release")
    db_session.add(newer)
    await db_session.flush()
    with pytest.raises(ValueError, match="compare_and_swap_failed"):
        await store.apply(
            shadow.model_copy(
                update={
                    "command_id": "cmd-4",
                    "action": "rollback",
                    "approval_id": "approval-rollback",
                }
            )
        )
    retired_baseline = await db_session.get(EvolutionSkillConfig, baseline.id)
    assert retired_baseline is not None and retired_baseline.status == "retired"
    assert newer.status == "active"


@pytest.mark.asyncio
async def test_canary_rollback_keeps_baseline_live(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    shadow = _command(baseline, candidate)
    await store.apply(shadow)
    canary = shadow.model_copy(
        update={"command_id": "cmd-2", "action": "canary", "approval_id": "approval-1"}
    )
    await store.apply(canary)
    rollback = shadow.model_copy(
        update={"command_id": "cmd-3", "action": "rollback", "approval_id": "approval-rollback"}
    )
    assert (await store.apply(rollback))["state"] == "rolled_back"
    restored_baseline = await db_session.get(EvolutionSkillConfig, baseline.id)
    unchanged_candidate = await db_session.get(EvolutionSkillConfig, candidate.id)
    assert restored_baseline is not None and restored_baseline.status == "active"
    assert unchanged_candidate is not None and unchanged_candidate.status == "candidate"
    experiment = (
        await db_session.execute(
            select(EvolutionExperiment).where(EvolutionExperiment.experiment_id == "deploy-1")
        )
    ).scalar_one()
    assert experiment.status == "rolled_back"


@pytest.mark.asyncio
async def test_shadow_rollback_is_a_ledger_only_transition(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    shadow = _command(baseline, candidate)
    await store.apply(shadow)
    rollback = shadow.model_copy(
        update={"command_id": "cmd-2", "action": "rollback", "approval_id": "approval-rollback"}
    )
    assert (await store.apply(rollback))["state"] == "rolled_back"
    restored_baseline = await db_session.get(EvolutionSkillConfig, baseline.id)
    unchanged_candidate = await db_session.get(EvolutionSkillConfig, candidate.id)
    assert restored_baseline is not None and restored_baseline.status == "active"
    assert unchanged_candidate is not None and unchanged_candidate.status == "candidate"
    assert (await db_session.execute(select(EvolutionExperiment))).scalars().all() == []


@pytest.mark.asyncio
async def test_only_one_live_canary_per_company_and_skill(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    candidate_three = _skill(3, "candidate", "third candidate")
    db_session.add(candidate_three)
    await db_session.flush()
    store = SqlAlchemySkillReleaseStore(db_session)
    first = _command(baseline, candidate)
    await store.apply(first)
    await store.apply(
        first.model_copy(
            update={"command_id": "cmd-2", "action": "canary", "approval_id": "approval-1"}
        )
    )

    second = _command(
        baseline,
        candidate_three,
        command_id="cmd-3",
        deployment_id="deploy-2",
        candidate_version=3,
        candidate_config_hash=skill_config_hash(candidate_three),
    )
    await store.apply(second)
    with pytest.raises(ValueError, match="canary_already_running"):
        await store.apply(
            second.model_copy(
                update={"command_id": "cmd-4", "action": "canary", "approval_id": "approval-2"}
            )
        )


@pytest.mark.asyncio
async def test_promote_requires_declared_improvement(db_session: AsyncSession) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    shadow = _command(baseline, candidate)
    await store.apply(shadow)
    await store.apply(
        shadow.model_copy(
            update={"command_id": "cmd-2", "action": "canary", "approval_id": "approval-1"}
        )
    )
    experiment = (
        await db_session.execute(
            select(EvolutionExperiment).where(EvolutionExperiment.experiment_id == "deploy-1")
        )
    ).scalar_one()
    experiment.control_results = [0.8] * 50
    experiment.candidate_results = [0.84] * 50
    with pytest.raises(ValueError, match="quality_gate_failed"):
        await store.apply(
            shadow.model_copy(
                update={
                    "command_id": "cmd-3",
                    "action": "promote",
                    "approval_id": "approval-promote",
                }
            )
        )
    restored_baseline = await db_session.get(EvolutionSkillConfig, baseline.id)
    unchanged_candidate = await db_session.get(EvolutionSkillConfig, candidate.id)
    assert restored_baseline is not None and restored_baseline.status == "active"
    assert unchanged_candidate is not None and unchanged_candidate.status == "candidate"


@pytest.mark.asyncio
async def test_skill_config_version_read_returns_hash_without_configuration(
    db_session: AsyncSession,
) -> None:
    baseline, _ = await _seed(db_session)
    result = await SqlAlchemySkillReleaseStore(db_session).get_skill_config(
        baseline.skill_id, baseline.version
    )
    assert result == {
        "skill_id": baseline.skill_id,
        "version": baseline.version,
        "status": baseline.status,
        "target_model": baseline.target_model,
        "configuration_hash": skill_config_hash(baseline),
    }
    assert not {"system_prompt", "parameters", "few_shot_examples"} & result.keys()
    assert (
        await SqlAlchemySkillReleaseStore(db_session).get_skill_config(baseline.skill_id, "missing")
        is None
    )


@pytest.mark.asyncio
async def test_command_reconciliation_lookup_is_immutable_and_company_scoped(
    db_session: AsyncSession,
) -> None:
    baseline, candidate = await _seed(db_session)
    store = SqlAlchemySkillReleaseStore(db_session)
    command = _command(baseline, candidate)
    ack = await store.apply(command)
    persisted = await store.get_command(command.command_id)
    assert persisted == {
        "command_id": command.command_id,
        "deployment_id": command.deployment_id,
        "payload_hash": canonical_hash(command.model_dump(mode="json")),
        "response": ack,
    }
    assert await store.get_command("missing-command") is None
    release = await db_session.get(EvolutionSkillRelease, command.deployment_id)
    assert release is not None
    release.company_id = "cmp_other"
    await db_session.flush()
    assert await store.get_command(command.command_id) is None
    assert await store.get(command.deployment_id) is None
