"""Unit tests for operation log store wiring."""

import json

import pytest

from services.gateways.user_interaction.core.ops_logger import (
    configure_operation_log_store,
    record_op,
)


@pytest.fixture(autouse=True)
def reset_operation_log_store():
    configure_operation_log_store(None)
    yield
    configure_operation_log_store(None)


class FakeOperationLogStore:
    def __init__(self):
        self.records: list[dict] = []

    async def record(self, **kwargs) -> None:
        self.records.append(kwargs)


@pytest.mark.asyncio
async def test_record_op_uses_injected_store() -> None:
    store = FakeOperationLogStore()
    configure_operation_log_store(store)

    await record_op(
        user_id="ou_user_1",
        user_name="Alice",
        action="confirm_create",
        result="success",
        table_id="tbl_1",
        record_id="rec_1",
        fields={"DRI (负责人)": [{"name": "Bob"}], "任务(动宾短语)": "Build report"},
    )

    assert len(store.records) == 1
    record = store.records[0]
    assert record["user_id"] == "ou_user_1"
    assert record["assignee_name"] == "Bob"
    assert json.loads(record["fields_snapshot"])["任务(动宾短语)"] == "Build report"
