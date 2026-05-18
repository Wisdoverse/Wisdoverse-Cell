import pytest

from services.gateways.user_interaction.core.health_use_cases import (
    UserInteractionHealthUseCase,
)


class FakeHealthStore:
    def __init__(self, ready: bool):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


@pytest.mark.asyncio
async def test_health_check_reports_database_and_chat_service() -> None:
    use_case = UserInteractionHealthUseCase(
        health_store=FakeHealthStore(True),
        chat_service=object(),
    )

    result = await use_case.check()

    assert result == {"database": True, "chat_service": True}


@pytest.mark.asyncio
async def test_health_check_reports_missing_chat_service() -> None:
    use_case = UserInteractionHealthUseCase(
        health_store=FakeHealthStore(False),
        chat_service=None,
    )

    result = await use_case.check()

    assert result == {"database": False, "chat_service": False}
