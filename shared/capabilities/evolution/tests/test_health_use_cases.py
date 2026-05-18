from types import SimpleNamespace

import pytest

from shared.capabilities.evolution.core.health_use_cases import EvolutionHealthUseCase


class FakeHealthStore:
    def __init__(self, ready: bool):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


@pytest.mark.asyncio
async def test_health_check_reports_runtime_dependencies() -> None:
    use_case = EvolutionHealthUseCase(
        health_store=FakeHealthStore(True),
        event_bus=SimpleNamespace(is_connected=True),
        llm_gateway=object(),
        approval_service=object(),
        collaboration_enabled=False,
        approval_gateway=None,
    )

    result = await use_case.check()

    assert result == {
        "database": True,
        "event_bus": True,
        "llm_gateway": True,
        "control_plane_approval_service": True,
    }


@pytest.mark.asyncio
async def test_health_check_reports_missing_dependencies() -> None:
    use_case = EvolutionHealthUseCase(
        health_store=FakeHealthStore(False),
        event_bus=SimpleNamespace(is_connected=False),
        llm_gateway=None,
        approval_service=None,
        collaboration_enabled=False,
        approval_gateway=None,
    )

    result = await use_case.check()

    assert result == {
        "database": False,
        "event_bus": False,
        "llm_gateway": False,
        "control_plane_approval_service": False,
    }


@pytest.mark.asyncio
async def test_health_check_includes_collaboration_gateway_when_enabled() -> None:
    use_case = EvolutionHealthUseCase(
        health_store=FakeHealthStore(True),
        event_bus=SimpleNamespace(is_connected=True),
        llm_gateway=object(),
        approval_service=object(),
        collaboration_enabled=True,
        approval_gateway=None,
    )

    result = await use_case.check()

    assert result["collaboration_approval_gateway"] is False
