"""Owner-local selection and idempotent, version-bound canary observations."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.evolution.canary_router import CanaryRouter
from shared.evolution.release_contract import canonical_hash
from shared.evolution.skill_execution_contract import (
    SkillExecutionResult,
    SkillSelection,
    SkillSelectionRequest,
    selection_signature,
)

from .release_tables import EvolutionSkillRelease
from .repository import EvolutionRepository
from .tables import EvolutionExperiment, EvolutionTrace


class SqlAlchemySkillExecutionStore:
    def __init__(self, session: AsyncSession, secret: str) -> None:
        self._session = session
        self._secret = secret

    async def resolve(self, request: SkillSelectionRequest) -> SkillSelection | None:
        if request.company_id != settings.control_plane_company_id:
            raise ValueError("release_company_not_owned")
        repo = EvolutionRepository(self._session)
        active = await repo.get_active_skill(request.skill_id)
        if active is None:
            return None
        active_version = int(active.version)
        release = await self._session.scalar(
            select(EvolutionSkillRelease)
            .where(
                EvolutionSkillRelease.company_id == request.company_id,
                EvolutionSkillRelease.agent_id == request.agent_id,
                EvolutionSkillRelease.skill_id == request.skill_id,
                or_(
                    and_(
                        EvolutionSkillRelease.state == "canary",
                        EvolutionSkillRelease.baseline_version == active_version,
                    ),
                    and_(
                        EvolutionSkillRelease.state == "active",
                        EvolutionSkillRelease.candidate_version == active_version,
                    ),
                    and_(
                        EvolutionSkillRelease.state == "rolled_back",
                        EvolutionSkillRelease.baseline_version == active_version,
                    ),
                ),
            )
            .order_by(
                case(
                    (EvolutionSkillRelease.state == "canary", 0),
                    (EvolutionSkillRelease.state == "active", 1),
                    else_=2,
                ),
                EvolutionSkillRelease.updated_at.desc(),
            )
            .limit(1)
        )
        if release is None:
            return None
        version = active_version
        if release.state == "canary":
            version = int(
                await CanaryRouter(repo=repo).resolve_skill_version(
                    request.agent_id, request.skill_id, request.trace_id
                )
            )
        config = await repo.get_skill_by_version(request.skill_id, str(version))
        if config is None:
            raise ValueError("release_skill_version_missing")
        configuration = {
            "skill_id": config.skill_id,
            "version": str(config.version),
            "system_prompt": config.system_prompt,
            "parameters": config.parameters or {},
            "few_shot_examples": config.few_shot_examples or [],
            "output_format": config.output_format or "",
            "target_model": config.target_model or "",
        }
        digest = canonical_hash(configuration)
        expected_hash = (
            release.candidate_config_hash
            if version == release.candidate_version
            else release.baseline_config_hash
        )
        if digest != expected_hash:
            raise ValueError("release_skill_config_hash_mismatch")
        data: dict[str, Any] = {
            **request.model_dump(mode="json"),
            "schema_version": "1.0",
            "deployment_id": release.deployment_id,
            "experiment_id": release.experiment_id if release.state == "canary" else None,
            "version": version,
            "configuration_hash": digest,
            "configuration": configuration,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
        # Canonicalize datetime spelling before signing the contract.
        selection = SkillSelection.model_validate({**data, "signature": "0" * 64})
        return selection.model_copy(
            update={
                "signature": selection_signature(selection.model_dump(mode="json"), self._secret)
            }
        )

    async def record(self, result: SkillExecutionResult) -> dict[str, Any]:
        selection = result.selection
        if selection.company_id != settings.control_plane_company_id:
            raise ValueError("release_company_not_owned")
        if selection.experiment_id is None:
            return {"state": "active", "recorded": False}
        release = await self._session.scalar(
            select(EvolutionSkillRelease)
            .where(EvolutionSkillRelease.deployment_id == selection.deployment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        experiment = await self._session.scalar(
            select(EvolutionExperiment)
            .where(EvolutionExperiment.experiment_id == selection.experiment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            experiment is None
            or release is None
            or release.company_id != selection.company_id
            or release.state != "canary"
            or experiment.status != "running"
            or experiment.agent_id != selection.agent_id
            or experiment.skill_id != selection.skill_id
            or release.experiment_id != experiment.experiment_id
        ):
            raise ValueError("release_experiment_not_running")
        repo = EvolutionRepository(self._session)
        expected_version = await CanaryRouter(repo=repo).resolve_skill_version(
            selection.agent_id, selection.skill_id, selection.trace_id
        )
        if expected_version != selection.version:
            raise ValueError("release_executed_version_mismatch")
        expected_hash = (
            release.candidate_config_hash
            if selection.version == release.candidate_version
            else release.baseline_config_hash
        )
        if expected_hash != selection.configuration_hash:
            raise ValueError("release_skill_config_hash_mismatch")
        prior = await self._session.scalar(
            select(EvolutionTrace)
            .where(
                EvolutionTrace.trace_id == selection.trace_id,
                EvolutionTrace.agent_id == selection.agent_id,
                EvolutionTrace.skill_used == selection.skill_id,
            )
            .limit(1)
        )
        if prior is not None and prior.auto_score is not None:
            if (
                str(prior.skill_version) != str(selection.version)
                or prior.auto_score != result.score
            ):
                raise ValueError("release_execution_result_conflict")
            return {"state": "canary", "recorded": False}
        # The experiment lock serializes deduplication and score-array appends.
        if prior is None:
            await repo.save_trace(
                trace_id=selection.trace_id,
                agent_id=selection.agent_id,
                event_type="evolution.skill.executed",
                success=result.success,
                skill_used=selection.skill_id,
                skill_version=str(selection.version),
                auto_score=result.score,
            )
        else:
            if str(prior.skill_version) != str(selection.version):
                raise ValueError("release_execution_result_conflict")
            prior.auto_score = result.score
            prior.success = result.success
            await self._session.flush()
        await repo.add_experiment_result(
            experiment.experiment_id,
            is_candidate=selection.version == experiment.candidate_version,
            score=result.score,
        )
        return {"state": "canary", "recorded": True}
