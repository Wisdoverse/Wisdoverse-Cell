import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from shared.capabilities.evolution.core.skill_execution import SkillExecutionUseCase
from shared.config import settings
from shared.evolution.db.release_tables import EvolutionSkillRelease
from shared.evolution.db.repository import EvolutionRepository
from shared.evolution.db.skill_execution_store import SqlAlchemySkillExecutionStore
from shared.evolution.db.tables import EvolutionExperiment, EvolutionTrace
from shared.evolution.release_contract import canonical_hash
from shared.evolution.skill_execution_contract import (
    SkillExecutionResult,
    SkillSelection,
    SkillSelectionRequest,
    selection_signature,
    verify_selection,
)

_SECRET = "frozen-skill-selection-signing-key-long-enough"
_CONFIGS = {
    1: {
        "skill_id": "agent:review",
        "version": "1",
        "system_prompt": "control system prompt",
        "parameters": {"temperature": 0.1, "max_tokens": 321},
        "few_shot_examples": [{"input": "x", "output": "y"}],
        "output_format": "json",
        "target_model": "openai/gpt-test",
    },
    2: {
        "skill_id": "agent:review",
        "version": "2",
        "system_prompt": "candidate system prompt",
        "parameters": {"temperature": 0.4, "max_tokens": 654},
        "few_shot_examples": [{"input": "a", "output": "b"}],
        "output_format": "json",
        "target_model": "openai/gpt-test",
    },
}


def _candidate_trace_id() -> str:
    import hashlib

    for i in range(10000):
        trace_id = f"candidate-trace-{i}"
        if int(hashlib.md5(trace_id.encode()).hexdigest()[:8], 16) % 100 < 10:
            return trace_id
    raise AssertionError("unable to find deterministic candidate trace")


@pytest.mark.asyncio
async def test_resolve_returns_frozen_version_and_record_dedupes_score_zero(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "control_plane_company_id", "owned-company")
    repo = EvolutionRepository(db_session)
    for version, config in _CONFIGS.items():
        await repo.save_skill_config(
            skill_id=config["skill_id"],
            version=str(version),
            status="active" if version == 1 else "candidate",
            system_prompt=config["system_prompt"],
            parameters=config["parameters"],
            few_shot_examples=config["few_shot_examples"],
            output_format=config["output_format"],
            target_model=config["target_model"],
        )
    db_session.add(
        EvolutionExperiment(
            experiment_id="exp-skill",
            agent_id="agent",
            skill_id="agent:review",
            control_version=1,
            candidate_version=2,
            traffic_pct=10,
            min_samples=50,
            status="running",
            control_results=[],
            candidate_results=[],
        )
    )
    db_session.add(
        EvolutionSkillRelease(
            deployment_id="dep-skill",
            company_id="owned-company",
            proposal_id="proposal",
            evaluation_report_id="report",
            evaluation_hash="d" * 64,
            skill_id="agent:review",
            agent_id="agent",
            baseline_version=1,
            candidate_version=2,
            baseline_config_hash=canonical_hash(_CONFIGS[1]),
            candidate_config_hash=canonical_hash(_CONFIGS[2]),
            state="canary",
            version=1,
            experiment_id="exp-skill",
        )
    )
    await db_session.flush()
    store = SqlAlchemySkillExecutionStore(db_session, _SECRET)
    trace_id = _candidate_trace_id()
    request = SkillSelectionRequest(
        company_id="owned-company",
        agent_id="agent",
        skill_id="agent:review",
        trace_id=trace_id,
    )
    selection = await store.resolve(request)
    assert selection is not None
    assert selection.version == 2
    assert selection.configuration == _CONFIGS[2]
    assert selection.configuration_hash == canonical_hash(_CONFIGS[2])
    verify_selection(selection, _SECRET)
    control_trace_id = next(
        f"control-trace-{i}"
        for i in range(10000)
        if int(hashlib.md5(f"control-trace-{i}".encode()).hexdigest()[:8], 16) % 100 >= 10
    )
    control = await store.resolve(
        SkillSelectionRequest(
            company_id="owned-company",
            agent_id="agent",
            skill_id="agent:review",
            trace_id=control_trace_id,
        )
    )
    assert control is not None
    assert control.version == 1
    assert control.configuration == _CONFIGS[1]

    # A trace persisted by the wrapper before its result callback is recoverable in place.
    db_session.add(
        EvolutionTrace(
            trace_id=trace_id,
            agent_id="agent",
            event_type="test.event",
            started_at=datetime.now(UTC),
            success=True,
            skill_used=selection.skill_id,
            skill_version=str(selection.version),
            auto_score=None,
        )
    )
    await db_session.flush()

    result = SkillExecutionResult(selection=selection, score=0.0, success=False)
    assert await store.record(result) == {"state": "canary", "recorded": True}
    assert await store.record(result) == {"state": "canary", "recorded": False}
    experiment = await db_session.scalar(
        select(EvolutionExperiment).where(EvolutionExperiment.experiment_id == "exp-skill")
    )
    assert experiment.candidate_results == [0.0]
    trace = await db_session.scalar(
        select(EvolutionTrace).where(EvolutionTrace.trace_id == trace_id)
    )
    assert trace.auto_score == 0.0
    trace_count = await db_session.scalar(
        select(func.count()).select_from(EvolutionTrace).where(EvolutionTrace.trace_id == trace_id)
    )
    assert trace_count == 1

    with pytest.raises(ValueError, match="release_execution_result_conflict"):
        await store.record(SkillExecutionResult(selection=selection, score=0.8, success=True))

    wrong_version = selection.model_copy(update={"version": 1})
    with pytest.raises(ValueError, match="release_executed_version_mismatch"):
        await store.record(SkillExecutionResult(selection=wrong_version, score=0.0, success=False))

    deployment = await db_session.get(EvolutionSkillRelease, "dep-skill")
    deployment.state = "rolled_back"
    await db_session.flush()
    with pytest.raises(ValueError, match="release_experiment_not_running"):
        await store.record(result)
    restored = await store.resolve(
        SkillSelectionRequest(
            company_id="owned-company",
            agent_id="agent",
            skill_id="agent:review",
            trace_id=trace_id,
        )
    )
    assert restored is not None
    assert restored.version == 1
    assert restored.configuration == _CONFIGS[1]
    assert restored.experiment_id is None
    verify_selection(restored, _SECRET)


@pytest.mark.asyncio
async def test_skill_selection_rejects_wrong_owner_and_missing_active_skill(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "control_plane_company_id", "owned-company")
    store = SqlAlchemySkillExecutionStore(db_session, _SECRET)
    with pytest.raises(ValueError, match="release_company_not_owned"):
        await store.resolve(
            SkillSelectionRequest(
                company_id="other-company",
                agent_id="agent",
                skill_id="agent:review",
                trace_id="t1",
            )
        )

    # A ledger alone cannot supply an active executable configuration.
    db_session.add(
        EvolutionSkillRelease(
            deployment_id="dep-rolled-back",
            company_id="owned-company",
            proposal_id="proposal",
            evaluation_report_id="report",
            evaluation_hash="d" * 64,
            skill_id="agent:review",
            agent_id="agent",
            baseline_version=1,
            candidate_version=2,
            baseline_config_hash=canonical_hash(_CONFIGS[1]),
            candidate_config_hash=canonical_hash(_CONFIGS[2]),
            state="rolled_back",
            version=2,
            experiment_id="exp-old",
        )
    )
    await db_session.flush()
    assert (
        await store.resolve(
            SkillSelectionRequest(
                company_id="owned-company",
                agent_id="agent",
                skill_id="agent:review",
                trace_id="t2",
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_active_rollout_uses_actual_active_configuration(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "control_plane_company_id", "owned-company")
    repo = EvolutionRepository(db_session)
    await repo.save_skill_config(
        skill_id="agent:review",
        version="2",
        status="active",
        system_prompt=_CONFIGS[2]["system_prompt"],
        parameters=_CONFIGS[2]["parameters"],
        few_shot_examples=_CONFIGS[2]["few_shot_examples"],
        output_format="json",
        target_model="openai/gpt-test",
    )
    db_session.add(
        EvolutionSkillRelease(
            deployment_id="dep-active",
            company_id="owned-company",
            proposal_id="proposal",
            evaluation_report_id="report",
            evaluation_hash="d" * 64,
            skill_id="agent:review",
            agent_id="agent",
            baseline_version=1,
            candidate_version=2,
            baseline_config_hash=canonical_hash(_CONFIGS[1]),
            candidate_config_hash=canonical_hash(_CONFIGS[2]),
            state="active",
            version=3,
            experiment_id=None,
        )
    )
    # A more recently updated stale rollback cannot replace the active release.
    db_session.add(
        EvolutionSkillRelease(
            deployment_id="dep-stale-rollback",
            company_id="owned-company",
            proposal_id="proposal-old",
            evaluation_report_id="report-old",
            evaluation_hash="e" * 64,
            skill_id="agent:review",
            agent_id="agent",
            baseline_version=1,
            candidate_version=2,
            baseline_config_hash=canonical_hash(_CONFIGS[1]),
            candidate_config_hash=canonical_hash(_CONFIGS[2]),
            state="rolled_back",
            version=4,
            updated_at=datetime.now(UTC) + timedelta(minutes=1),
        )
    )
    await db_session.flush()
    store = SqlAlchemySkillExecutionStore(db_session, _SECRET)
    selection = await store.resolve(
        SkillSelectionRequest(
            company_id="owned-company",
            agent_id="agent",
            skill_id="agent:review",
            trace_id="control-trace",
        )
    )
    assert selection is not None
    assert selection.version == 2
    assert selection.deployment_id == "dep-active"
    assert selection.configuration == _CONFIGS[2]
    verify_selection(selection, _SECRET)
    assert await store.record(
        SkillExecutionResult(selection=selection, score=0.4, success=True)
    ) == {
        "state": "active",
        "recorded": False,
    }


@pytest.mark.asyncio
async def test_skill_execution_use_case_rejects_bad_signature_and_configuration_hash() -> None:
    class UnusedStore:
        async def record(self, result):
            raise AssertionError("invalid evidence reached store")

    configuration = dict(_CONFIGS[1])
    values = {
        "company_id": "owned-company",
        "agent_id": "agent",
        "skill_id": "agent:review",
        "trace_id": "trace-usecase",
        "schema_version": "1.0",
        "deployment_id": "dep",
        "experiment_id": "exp",
        "version": 1,
        "configuration": configuration,
        "configuration_hash": canonical_hash(configuration),
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "signature": "0" * 64,
    }
    provisional = SkillSelection.model_validate(values)
    values["signature"] = selection_signature(provisional.model_dump(mode="json"), _SECRET)
    selection = SkillSelection.model_validate(values)
    use_case = SkillExecutionUseCase(UnusedStore(), _SECRET)
    with pytest.raises(ValueError, match="evolution_skill_selection_signature_invalid"):
        await use_case.record(
            SkillExecutionResult(
                selection=selection.model_copy(update={"signature": "1" * 64}),
                score=0.5,
                success=True,
            )
        )

    changed = selection.model_dump(mode="json")
    changed["configuration_hash"] = "f" * 64
    changed["signature"] = "0" * 64
    changed["signature"] = selection_signature(changed, _SECRET)
    with pytest.raises(ValueError, match="evolution_skill_configuration_hash_mismatch"):
        await use_case.record(
            SkillExecutionResult(
                selection=SkillSelection.model_validate(changed),
                score=0.5,
                success=True,
            )
        )
