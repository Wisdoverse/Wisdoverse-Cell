"""Pure lifecycle rules for authenticated skill release commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReleaseState = Literal["shadow", "canary", "active", "rolled_back"]
ReleaseAction = Literal["shadow", "canary", "promote", "rollback"]


class SkillReleaseError(ValueError):
    """A release command is inconsistent with current runtime state."""


@dataclass(frozen=True, slots=True)
class SkillReleaseSnapshot:
    deployment_id: str
    skill_id: str
    agent_id: str
    baseline_version: int
    candidate_version: int
    baseline_config_hash: str
    candidate_config_hash: str
    state: ReleaseState
    version: int
    experiment_id: str | None = None


def transition(
    snapshot: SkillReleaseSnapshot | None,
    *,
    action: ReleaseAction,
    deployment_id: str,
    skill_id: str,
    agent_id: str,
    baseline_version: int,
    candidate_version: int,
    baseline_config_hash: str,
    candidate_config_hash: str,
    expected_version: int | None,
    experiment_id: str | None = None,
) -> SkillReleaseSnapshot:
    """Validate and calculate a next immutable release snapshot."""
    if snapshot is None:
        if action != "shadow" or expected_version not in (None, 0):
            raise SkillReleaseError("release_must_start_in_shadow")
        return SkillReleaseSnapshot(
            deployment_id,
            skill_id,
            agent_id,
            baseline_version,
            candidate_version,
            baseline_config_hash,
            candidate_config_hash,
            "shadow",
            1,
            None,
        )
    if expected_version is None or expected_version != snapshot.version:
        raise SkillReleaseError("release_version_conflict")
    immutable = (
        snapshot.deployment_id,
        snapshot.skill_id,
        snapshot.agent_id,
        snapshot.baseline_version,
        snapshot.candidate_version,
        snapshot.baseline_config_hash,
        snapshot.candidate_config_hash,
    )
    supplied = (
        deployment_id,
        skill_id,
        agent_id,
        baseline_version,
        candidate_version,
        baseline_config_hash,
        candidate_config_hash,
    )
    if immutable != supplied:
        raise SkillReleaseError("release_snapshot_changed")
    if action == "canary" and snapshot.state == "shadow":
        return SkillReleaseSnapshot(
            *immutable, "canary", snapshot.version + 1, experiment_id or snapshot.experiment_id
        )
    if action == "promote" and snapshot.state == "canary":
        return SkillReleaseSnapshot(
            *immutable, "active", snapshot.version + 1, snapshot.experiment_id
        )
    if action == "rollback" and snapshot.state in ("shadow", "canary", "active"):
        return SkillReleaseSnapshot(
            *immutable, "rolled_back", snapshot.version + 1, snapshot.experiment_id
        )
    if action == "shadow" and snapshot.state == "shadow":
        return snapshot
    raise SkillReleaseError("invalid_release_transition")
