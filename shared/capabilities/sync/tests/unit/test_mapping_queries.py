from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.sync.core.mapping_queries import SyncMappingQueryService


@pytest.mark.asyncio
async def test_list_mappings_returns_read_models():
    updated_at = datetime(2026, 5, 17, tzinfo=UTC)
    repository = AsyncMock()
    repository.list_all = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=1,
                op_work_package_id=1001,
                feishu_record_id="rec_1",
                op_project_id=2001,
                updated_at=updated_at,
            )
        ]
    )

    result = await SyncMappingQueryService(repository).list_mappings()

    assert len(result) == 1
    assert result[0].id == 1
    assert result[0].op_work_package_id == 1001
    assert result[0].feishu_record_id == "rec_1"
    assert result[0].op_project_id == 2001
    assert result[0].updated_at == updated_at
    repository.list_all.assert_awaited_once_with()
