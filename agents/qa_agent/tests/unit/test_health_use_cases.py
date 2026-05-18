import pytest

from agents.qa_agent.core.health_use_cases import QAHealthUseCase


class FakeHealthStore:
    def __init__(self, ready: bool):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


@pytest.mark.asyncio
async def test_health_check_reports_database_ready() -> None:
    use_case = QAHealthUseCase(health_store=FakeHealthStore(True))

    result = await use_case.check()

    assert result == {"database": True}


@pytest.mark.asyncio
async def test_health_check_reports_database_not_ready() -> None:
    use_case = QAHealthUseCase(health_store=FakeHealthStore(False))

    result = await use_case.check()

    assert result == {"database": False}
