"""Evolution runtime deployment boundary."""

from typing import Any, Protocol

from shared.evolution.release_contract import SkillReleaseCommand


class EvolutionDeploymentGateway(Protocol):
    async def apply(self, command: SkillReleaseCommand) -> dict[str, Any]: ...

    async def lookup(self, command: SkillReleaseCommand) -> dict[str, Any] | None: ...
