import pytest

from shared.capabilities.analysis.core.health_use_cases import AnalysisHealthUseCase


class FakeHealthStore:
    def __init__(self, ready: bool):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


@pytest.mark.asyncio
async def test_health_check_reports_database_and_event_bus() -> None:
    use_case = AnalysisHealthUseCase(
        health_store=FakeHealthStore(True),
        event_bus=object(),
    )

    result = await use_case.check()

    assert result == {"database": True, "event_bus": True}


@pytest.mark.asyncio
async def test_health_check_reports_missing_event_bus() -> None:
    use_case = AnalysisHealthUseCase(
        health_store=FakeHealthStore(False),
        event_bus=None,
    )

    result = await use_case.check()

    assert result == {"database": False, "event_bus": False}
