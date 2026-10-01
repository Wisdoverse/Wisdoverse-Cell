"""Ports for the skill release application service."""

from typing import Any, Protocol

from shared.evolution.release_contract import SkillReleaseCommand


class SkillReleaseStore(Protocol):
    async def apply(self, command: SkillReleaseCommand) -> dict[str, Any]: ...
    async def get(self, deployment_id: str) -> dict[str, Any] | None: ...
    async def get_command(
        self,
        command_id: str,
        *,
        skill_id: str | None = None,
        baseline_version: int | None = None,
        candidate_version: int | None = None,
    ) -> dict[str, Any] | None: ...
    async def get_skill_config(self, skill_id: str, version: str) -> dict[str, Any] | None: ...
