from types import SimpleNamespace

import pytest

from agents.pjm_agent.core.health_use_cases import PJMHealthUseCase


class FakeHealthStore:
    def __init__(self, ready: bool):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


@pytest.mark.asyncio
async def test_health_check_reports_database_and_config_loaded() -> None:
    use_case = PJMHealthUseCase(
        health_store=FakeHealthStore(True),
        config=SimpleNamespace(members=["pm"]),
    )

    result = await use_case.check()

    assert result == {"database": True, "config_loaded": True}


@pytest.mark.asyncio
async def test_health_check_reports_missing_config() -> None:
    use_case = PJMHealthUseCase(
        health_store=FakeHealthStore(True),
        config=None,
    )

    result = await use_case.check()

    assert result == {"database": True, "config_loaded": False}


@pytest.mark.asyncio
async def test_health_check_reports_empty_config_members() -> None:
    use_case = PJMHealthUseCase(
        health_store=FakeHealthStore(False),
        config=SimpleNamespace(members=[]),
    )

    result = await use_case.check()

    assert result == {"database": False, "config_loaded": False}
