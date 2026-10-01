"""SQLAlchemy adapter for atomic skill release command application."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.evolution.domain.skill_release import (
    ReleaseState,
    SkillReleaseError,
    SkillReleaseSnapshot,
    transition,
)
from shared.evolution.release_contract import (
    SkillReleaseCommand,
    canonical_hash,
    skill_config_hash,
)

from .release_tables import EvolutionSkillRelease, EvolutionSkillReleaseCommand
from .tables import EvolutionExperiment, EvolutionSkillConfig


class ReleaseCommandConflict(ValueError):
    """The command id has already been used with a different payload."""


class ReleaseOwnershipError(ValueError):
    """A command does not belong to this runtime's configured company."""


class SqlAlchemySkillReleaseStore:
    """Apply command, release ledger, skills, and experiment in one transaction."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def apply(self, command: SkillReleaseCommand) -> dict[str, Any]:
        if command.company_id != settings.control_plane_company_id:
            raise ReleaseOwnershipError("release_company_not_owned")
        payload_hash = canonical_hash(command.model_dump(mode="json"))
        prior = await self._session.get(EvolutionSkillReleaseCommand, command.command_id)
        if prior is not None:
            if prior.payload_hash != payload_hash:
                raise ReleaseCommandConflict("release_command_id_payload_conflict")
            return prior.response
        if command.action in {"promote", "rollback"} and not command.approval_id:
            raise SkillReleaseError("release_live_action_approval_required")

        # Lock both skill snapshots in a deterministic order. This also serializes
        # first-time deployment commands for the same skill on PostgreSQL.
        skill_result = await self._session.execute(
            select(EvolutionSkillConfig)
            .where(
                EvolutionSkillConfig.skill_id == command.skill_id,
                EvolutionSkillConfig.version.in_(
                    (str(command.baseline_version), str(command.candidate_version))
                ),
            )
            .order_by(EvolutionSkillConfig.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        skill_rows = list(skill_result.scalars().all())
        by_version = {str(row.version): row for row in skill_rows}
        baseline = by_version.get(str(command.baseline_version))
        candidate = by_version.get(str(command.candidate_version))
        if baseline is None or candidate is None:
            raise SkillReleaseError("release_skill_version_missing")
        if baseline.id == candidate.id:
            raise SkillReleaseError("release_versions_must_differ")

        # Skill-row locks serialize requests; recheck replay and deployment after
        # acquiring them so waiters observe the first writer's committed ledger.
        prior = await self._session.get(EvolutionSkillReleaseCommand, command.command_id)
        if prior is not None:
            if prior.payload_hash != payload_hash:
                raise ReleaseCommandConflict("release_command_id_payload_conflict")
            return prior.response
        # Recheck expiry after waiting for ownership locks. A receipt lookup
        # using these same locks can now prove an expired command is unapplied.
        if command.expires_at.tzinfo is None or command.expires_at.astimezone(UTC) <= datetime.now(
            UTC
        ):
            raise SkillReleaseError("evolution_command_expired")
        release_result = await self._session.execute(
            select(EvolutionSkillRelease)
            .where(EvolutionSkillRelease.deployment_id == command.deployment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        release = release_result.scalar_one_or_none()

        if (
            skill_config_hash(baseline) != command.baseline_config_hash
            or skill_config_hash(candidate) != command.candidate_config_hash
        ):
            raise SkillReleaseError("release_skill_config_hash_mismatch")
        if release is None and command.action == "shadow":
            if baseline.status != "active":
                raise SkillReleaseError("release_baseline_not_active")
            if candidate.status not in {"candidate", "shadow", "retired"}:
                raise SkillReleaseError("release_candidate_unavailable")
        elif release is not None:
            if release.company_id != command.company_id:
                raise ReleaseOwnershipError("release_company_not_owned")
            if (release.proposal_id, release.evaluation_report_id, release.evaluation_hash) != (
                command.proposal_id,
                command.evaluation_report_id,
                command.evaluation_hash,
            ):
                raise SkillReleaseError("release_evaluation_snapshot_changed")
            if release.version < 1:
                raise SkillReleaseError("release_version_conflict")

        exp = None
        exp_id = release.experiment_id if release is not None else None
        if command.action == "canary":
            if not command.approval_id:
                raise SkillReleaseError("release_canary_approval_required")
            exp_id = command.deployment_id
            other_canary_result = await self._session.execute(
                select(EvolutionSkillRelease.deployment_id)
                .where(
                    EvolutionSkillRelease.company_id == command.company_id,
                    EvolutionSkillRelease.skill_id == command.skill_id,
                    EvolutionSkillRelease.state == "canary",
                    EvolutionSkillRelease.deployment_id != command.deployment_id,
                )
                .limit(1)
            )
            if other_canary_result.scalar_one_or_none() is not None:
                raise SkillReleaseError("release_skill_canary_already_running")
            exp_result = await self._session.execute(
                select(EvolutionExperiment)
                .where(EvolutionExperiment.experiment_id == exp_id)
                .with_for_update()
            )
            exp = exp_result.scalar_one_or_none()
            if exp is None:
                if release is None or release.state != "shadow" or baseline.status != "active":
                    raise SkillReleaseError("release_canary_requires_shadow")
                exp = EvolutionExperiment(
                    experiment_id=exp_id,
                    agent_id=command.agent_id,
                    skill_id=command.skill_id,
                    control_version=command.baseline_version,
                    candidate_version=command.candidate_version,
                    traffic_pct=min(command.traffic_pct, 10),
                    min_samples=max(command.minimum_sample_count, 50),
                    max_duration_hours=72,
                    success_metric="success_rate",
                    min_improvement=0.05,
                    status="running",
                    control_results=[],
                    candidate_results=[],
                )
                self._session.add(exp)
                await self._session.flush()
            else:
                if (exp.agent_id, exp.skill_id, exp.control_version, exp.candidate_version) != (
                    command.agent_id,
                    command.skill_id,
                    command.baseline_version,
                    command.candidate_version,
                ):
                    raise SkillReleaseError("release_experiment_snapshot_changed")
                if exp.status != "running":
                    raise SkillReleaseError("release_experiment_not_running")
                exp.traffic_pct = min(command.traffic_pct, 10)
                exp.min_samples = max(command.minimum_sample_count, 50)

        current = None
        if release is not None:
            current = SkillReleaseSnapshot(
                release.deployment_id,
                release.skill_id,
                release.agent_id,
                release.baseline_version,
                release.candidate_version,
                release.baseline_config_hash,
                release.candidate_config_hash,
                cast(ReleaseState, release.state),
                release.version,
                release.experiment_id,
            )
        next_release = transition(
            current,
            action=command.action,
            deployment_id=command.deployment_id,
            skill_id=command.skill_id,
            agent_id=command.agent_id,
            baseline_version=command.baseline_version,
            candidate_version=command.candidate_version,
            baseline_config_hash=command.baseline_config_hash,
            candidate_config_hash=command.candidate_config_hash,
            expected_version=current.version if current else 0,
            experiment_id=exp_id,
        )

        if command.action == "promote":
            if current is None or current.state != "canary":
                raise SkillReleaseError("release_promotion_requires_canary")
            if exp is None:
                exp_result = await self._session.execute(
                    select(EvolutionExperiment)
                    .where(EvolutionExperiment.experiment_id == current.experiment_id)
                    .with_for_update()
                )
                exp = exp_result.scalar_one_or_none()
            if exp is None or exp.status != "running":
                raise SkillReleaseError("release_experiment_not_running")
            min_samples = max(command.minimum_sample_count, exp.min_samples, 50)
            control_scores = list(exp.control_results or [])
            candidate_scores = list(exp.candidate_results or [])
            if len(control_scores) < min_samples or len(candidate_scores) < min_samples:
                raise SkillReleaseError("release_canary_minimum_sample_count_not_met")
            if not control_scores or not candidate_scores:
                raise SkillReleaseError("release_canary_quality_data_missing")
            if (
                sum(candidate_scores) / len(candidate_scores)
                < sum(control_scores) / len(control_scores) + exp.min_improvement
            ):
                raise SkillReleaseError("release_canary_quality_gate_failed")
            if baseline.status != "active" or candidate.status not in {"candidate", "shadow"}:
                raise SkillReleaseError("release_skill_compare_and_swap_failed")
            changed = cast(
                CursorResult[Any],
                await self._session.execute(
                    update(EvolutionSkillConfig)
                    .where(
                        EvolutionSkillConfig.id == baseline.id,
                        EvolutionSkillConfig.status == "active",
                    )
                    .values(status="retired")
                ),
            )
            if changed.rowcount != 1:
                raise SkillReleaseError("release_skill_compare_and_swap_failed")
            changed = cast(
                CursorResult[Any],
                await self._session.execute(
                    update(EvolutionSkillConfig)
                    .where(
                        EvolutionSkillConfig.id == candidate.id,
                        EvolutionSkillConfig.status == candidate.status,
                    )
                    .values(status="active", promoted_at=datetime.now(UTC))
                ),
            )
            if changed.rowcount != 1:
                raise SkillReleaseError("release_skill_compare_and_swap_failed")
            exp.status, exp.concluded_at = "promoted", datetime.now(UTC)
        elif command.action == "rollback":
            if current is None:
                raise SkillReleaseError("release_not_found")
            if current.state == "shadow":
                # A shadow release has no experiment or live effects to undo.
                pass
            elif current.state == "canary":
                if exp is None:
                    exp_result = await self._session.execute(
                        select(EvolutionExperiment)
                        .where(EvolutionExperiment.experiment_id == current.experiment_id)
                        .with_for_update()
                    )
                    exp = exp_result.scalar_one_or_none()
                if exp is not None and exp.status == "running":
                    exp.status, exp.concluded_at = "rolled_back", datetime.now(UTC)
            elif current.state == "active":
                if exp is None:
                    exp_result = await self._session.execute(
                        select(EvolutionExperiment)
                        .where(EvolutionExperiment.experiment_id == current.experiment_id)
                        .with_for_update()
                    )
                    exp = exp_result.scalar_one_or_none()
                # Only undo this release while its candidate remains the live version.
                if candidate.status != "active" or baseline.status != "retired":
                    raise SkillReleaseError("release_skill_compare_and_swap_failed")
                changed = cast(
                    CursorResult[Any],
                    await self._session.execute(
                        update(EvolutionSkillConfig)
                        .where(
                            EvolutionSkillConfig.id == candidate.id,
                            EvolutionSkillConfig.status == "active",
                        )
                        .values(status="retired")
                    ),
                )
                if changed.rowcount != 1:
                    raise SkillReleaseError("release_skill_compare_and_swap_failed")
                changed = cast(
                    CursorResult[Any],
                    await self._session.execute(
                        update(EvolutionSkillConfig)
                        .where(
                            EvolutionSkillConfig.id == baseline.id,
                            EvolutionSkillConfig.status == "retired",
                        )
                        .values(status="active")
                    ),
                )
                if changed.rowcount != 1:
                    raise SkillReleaseError("release_skill_compare_and_swap_failed")
                if exp is not None and exp.status == "promoted":
                    exp.status, exp.concluded_at = "rolled_back", datetime.now(UTC)
            else:
                raise SkillReleaseError("invalid_release_transition")

        if release is None:
            release = EvolutionSkillRelease(
                deployment_id=command.deployment_id,
                company_id=command.company_id,
                proposal_id=command.proposal_id,
                evaluation_report_id=command.evaluation_report_id,
                evaluation_hash=command.evaluation_hash,
                skill_id=command.skill_id,
                agent_id=command.agent_id,
                baseline_version=command.baseline_version,
                candidate_version=command.candidate_version,
                baseline_config_hash=command.baseline_config_hash,
                candidate_config_hash=command.candidate_config_hash,
                state=next_release.state,
                version=next_release.version,
                experiment_id=next_release.experiment_id,
            )
            self._session.add(release)
        else:
            # The SELECT lock serializes PostgreSQL writers; version predicate is
            # retained as a compare-and-swap guard for all supported databases.
            if current is None:
                raise SkillReleaseError("release_version_conflict")
            result = cast(
                CursorResult[Any],
                await self._session.execute(
                    update(EvolutionSkillRelease)
                    .where(
                        EvolutionSkillRelease.deployment_id == command.deployment_id,
                        EvolutionSkillRelease.version == current.version,
                    )
                    .values(
                        state=next_release.state,
                        version=next_release.version,
                        experiment_id=next_release.experiment_id,
                        updated_at=datetime.now(UTC),
                    )
                ),
            )
            if result.rowcount != 1:
                raise SkillReleaseError("release_version_conflict")

        response = {
            "deployment_id": next_release.deployment_id,
            "state": next_release.state,
            "version": next_release.version,
            "experiment_id": next_release.experiment_id,
        }
        self._session.add(
            EvolutionSkillReleaseCommand(
                command_id=command.command_id,
                deployment_id=command.deployment_id,
                payload_hash=payload_hash,
                response=response,
            )
        )
        await self._session.flush()
        return response

    async def get(self, deployment_id: str) -> dict[str, Any] | None:
        row = await self._session.get(EvolutionSkillRelease, deployment_id)
        if row is None or row.company_id != settings.control_plane_company_id:
            return None
        return {
            "deployment_id": row.deployment_id,
            "company_id": row.company_id,
            "proposal_id": row.proposal_id,
            "evaluation_report_id": row.evaluation_report_id,
            "evaluation_hash": row.evaluation_hash,
            "skill_id": row.skill_id,
            "agent_id": row.agent_id,
            "baseline_version": row.baseline_version,
            "candidate_version": row.candidate_version,
            "baseline_config_hash": row.baseline_config_hash,
            "candidate_config_hash": row.candidate_config_hash,
            "state": row.state,
            "version": row.version,
            "experiment_id": row.experiment_id,
        }

    async def get_command(
        self,
        command_id: str,
        *,
        skill_id: str | None = None,
        baseline_version: int | None = None,
        candidate_version: int | None = None,
    ) -> dict[str, Any] | None:
        if skill_id is not None:
            await self._session.execute(
                select(EvolutionSkillConfig)
                .where(
                    EvolutionSkillConfig.skill_id == skill_id,
                    EvolutionSkillConfig.version.in_(
                        (str(baseline_version), str(candidate_version))
                    ),
                )
                .order_by(EvolutionSkillConfig.id)
                .with_for_update()
            )
        command = await self._session.get(EvolutionSkillReleaseCommand, command_id)
        if command is None:
            return None
        release = await self._session.get(EvolutionSkillRelease, command.deployment_id)
        if release is None or release.company_id != settings.control_plane_company_id:
            return None
        return {
            "command_id": command.command_id,
            "deployment_id": command.deployment_id,
            "payload_hash": command.payload_hash,
            "response": command.response,
        }

    async def get_skill_config(self, skill_id: str, version: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(EvolutionSkillConfig).where(
                EvolutionSkillConfig.skill_id == skill_id,
                EvolutionSkillConfig.version == version,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "skill_id": row.skill_id,
            "version": row.version,
            "status": row.status,
            "target_model": row.target_model,
            "configuration_hash": skill_config_hash(row),
        }
