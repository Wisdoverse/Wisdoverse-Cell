from types import SimpleNamespace

import pytest

from agents.requirement_manager.core.health_use_cases import RequirementHealthUseCase


class FakeHealthStore:
    def __init__(self, ready: bool):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


@pytest.mark.asyncio
async def test_health_check_reports_runtime_dependencies() -> None:
    use_case = RequirementHealthUseCase(
        health_store=FakeHealthStore(True),
        event_bus=SimpleNamespace(is_connected=True),
        messenger=object(),
        card_renderer=object(),
    )

    result = await use_case.check()

    assert result == {
        "database": True,
        "event_bus": True,
        "messenger": True,
        "card_renderer": True,
    }


@pytest.mark.asyncio
async def test_health_check_reports_missing_optional_dependencies() -> None:
    use_case = RequirementHealthUseCase(
        health_store=FakeHealthStore(False),
        event_bus=SimpleNamespace(is_connected=False),
        messenger=None,
        card_renderer=None,
    )

    result = await use_case.check()

    assert result == {
        "database": False,
        "event_bus": False,
        "messenger": False,
        "card_renderer": False,
    }
