"""Policy boundary for authenticated skill release commands."""

from typing import Any

from shared.evolution.release_contract import SkillReleaseCommand, verify_command

from .release_ports import SkillReleaseStore


class SkillReleaseUseCase:
    def __init__(self, store: SkillReleaseStore, signing_secret: str):
        self._store = store
        self._signing_secret = signing_secret

    async def apply(self, command: SkillReleaseCommand, signature: str) -> dict[str, Any]:
        verify_command(command, signature, self._signing_secret)
        return await self._store.apply(command)

    async def get(self, deployment_id: str) -> dict[str, Any] | None:
        return await self._store.get(deployment_id)

    async def get_command(
        self,
        command_id: str,
        *,
        skill_id: str | None = None,
        baseline_version: int | None = None,
        candidate_version: int | None = None,
    ) -> dict[str, Any] | None:
        if skill_id is None:
            return await self._store.get_command(command_id)
        return await self._store.get_command(
            command_id,
            skill_id=skill_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
        )

    async def get_skill_config(self, skill_id: str, version: str) -> dict[str, Any] | None:
        return await self._store.get_skill_config(skill_id, version)
