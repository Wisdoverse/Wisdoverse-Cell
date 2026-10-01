"""Native runtime HTTP contracts against isolated owner-local receipt databases."""

import asyncio
from importlib import import_module
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.app.native_executor import NativeExecutorUseCase
from shared.config import settings
from shared.core.native_executor import NativeExecutorError
from shared.infra.native_executor_store import SqlAlchemyNativeExecutorLedger
from shared.protocols.executor import ExecutorRequest

OWNERS = [
    ("requirement_manager", "ingest", {"content": "Synthetic requirements"}),
    ("pjm_agent", "get_decompose", {"wp_id": 123}),
    ("dev_agent", "get_task_status", {"wp_id": 123}),
    ("qa_agent", "get_run", {"run_id": "native-qa-run"}),
]


def _command(action="ingest", fields=None):
    return {
        "schema_version": "1.0",
        "company_id": "cmp_executor_contract",
        "agent_id": "role_delivery",
        "run_id": "run_executor_contract",
        "trace_id": "trace_executor_contract",
        "goal_id": "goal_delivery",
        "work_item_id": "work_delivery",
        "action": "wakeup",
        "input": {"action": action, **(fields or {})},
        "max_cost_usd": 0.25,
    }


_HEADERS = {
    "X-Executor-Contract": "1.0",
    "Idempotency-Key": "run_executor_contract",
    "X-Trace-ID": "trace_executor_contract",
    "X-Internal-Key": "executor-test-key",
}


@pytest.fixture
async def owner_client(request, tmp_path, monkeypatch):
    owner, action, fields = request.param
    app = import_module(f"agents.{owner}.app.main").app
    module = import_module(f"agents.{owner}.db.executor_ledger")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / (owner + '.sqlite')}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(module.executor_ledger, "_sessions", sessions)
    await module.executor_ledger.initialize()
    handler = AsyncMock(
        return_value={
            "status": "passed",
            "run_id": "native-result-id",
            "summary": "Synthetic native result",
        }
    )
    monkeypatch.setattr(app.state.runtime.agent, "handle_request", handler)
    monkeypatch.setattr(settings, "native_executor_enabled", True)
    monkeypatch.setattr(settings, "control_plane_company_id", "cmp_executor_contract")
    monkeypatch.setattr(settings, "internal_service_key", "executor-test-key")
    monkeypatch.setattr(settings, "pm_api_key", "")
    monkeypatch.setattr(settings, "app_env", "test")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://native.test"
    ) as client:
        yield client, module, handler, _command(action, fields)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS, indirect=True)
async def test_native_owner_dispatch_and_replay_across_http_entrypoints(owner_client):
    client, module, handler, command = owner_client
    first = await client.post("/api/v1/executor/requests", json=command, headers=_HEADERS)
    assert first.status_code == 200, first.text
    response = first.json()
    assert response["status"] == "recorded"  # Native 'passed' is not delivery acceptance.
    assert response["cost_is_estimate"] is True
    assert response["cost_usd"] == 0.25
    assert response["artifact_references"] == []
    dispatched = handler.call_args.args[0]
    assert dispatched["action"] == command["input"]["action"]
    assert dispatched["trace_id"] == command["trace_id"]
    assert dispatched["_executor_context"]["run_id"] == command["run_id"]
    if command["input"].get("run_id"):
        assert dispatched["run_id"] == "native-qa-run"
    # The legacy URL carries the same durable contract when the version header is present.
    replay = await client.post("/agent/request", json=command, headers=_HEADERS)
    assert replay.status_code == 200
    assert replay.json() == response
    assert handler.await_count == 1
    fresh_ledger = SqlAlchemyNativeExecutorLedger(
        module.executor_ledger._sessions, module.executor_table
    )
    receipt = await fresh_ledger.lookup(command["company_id"], command["run_id"])
    assert receipt.response.model_dump(mode="json") == response
    lookup = await client.get(
        f"/api/v1/executor/requests/{command['run_id']}",
        params={"company_id": command["company_id"]},
        headers=_HEADERS,
    )
    assert lookup.json()["state"] == "recorded"
    foreign = await client.get(
        f"/api/v1/executor/requests/{command['run_id']}",
        params={"company_id": "cmp_foreign"},
        headers=_HEADERS,
    )
    assert foreign.status_code == 403
    changed = {**command, "input": {**command["input"], "unexpected": "different"}}
    conflict = await client.post("/api/v1/executor/requests", json=changed, headers=_HEADERS)
    assert conflict.status_code == 409
    assert handler.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS, indirect=True)
async def test_native_denials_happen_before_business_dispatch(owner_client, monkeypatch):
    client, module, handler, command = owner_client
    cases = [
        ({**command, "company_id": "cmp_foreign"}, _HEADERS, 403),
        (command, {**_HEADERS, "Idempotency-Key": "wrong"}, 422),
        (command, {**_HEADERS, "X-Executor-Contract": "2.0"}, 422),
        (command, {**_HEADERS, "X-Trace-ID": "wrong"}, 422),
        ({**command, "input": {"action": "unsupported"}}, _HEADERS, 422),
        ({**command, "input": {**command["input"], "_executor_context": {}}}, _HEADERS, 422),
        ({**command, "extra": "forbidden"}, _HEADERS, 422),
    ]
    for body, headers, status in cases:
        response = await client.post("/api/v1/executor/requests", json=body, headers=headers)
        assert response.status_code == status, response.text
        assert "code" in response.json() and "trace_id" in response.json()
    no_auth = await client.post("/api/v1/executor/requests", json=command)
    assert no_auth.status_code == 401
    monkeypatch.setattr(settings, "native_executor_enabled", False)
    disabled = await client.post("/api/v1/executor/requests", json=command, headers=_HEADERS)
    assert disabled.status_code == 503
    assert handler.await_count == 0
    assert await module.executor_ledger.lookup(command["company_id"], command["run_id"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS, indirect=True)
async def test_native_uncertain_results_are_not_reexecuted(owner_client):
    client, module, handler, command = owner_client
    handler.side_effect = RuntimeError("secret-native-backend-detail")
    failed = await client.post("/api/v1/executor/requests", json=command, headers=_HEADERS)
    assert failed.status_code == 503
    assert "secret-native-backend-detail" not in failed.text
    replay = await client.post("/agent/request", json=command, headers=_HEADERS)
    assert replay.status_code == 503
    assert handler.await_count == 1
    receipt = await module.executor_ledger.lookup(command["company_id"], command["run_id"])
    assert receipt.state == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS, indirect=True)
async def test_native_legacy_requests_remain_unwrapped(owner_client):
    client, _, handler, command = owner_client
    response = await client.post(
        "/agent/request", json=command["input"], headers={"X-Internal-Key": "executor-test-key"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    assert "_executor_context" not in handler.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS[:1], indirect=True)
async def test_native_timeout_keeps_intent_after_effect(owner_client):
    _, module, handler, command = owner_client
    effect = []

    async def slow(_):
        effect.append("started")
        await asyncio.sleep(10)
        return {"status": "ok"}

    use_case = NativeExecutorUseCase(
        module.executor_ledger,
        slow,
        runtime_id="requirement-manager",
        company_id=command["company_id"],
        allowed_actions=frozenset({"ingest"}),
        timeout_seconds=0.02,
    )
    with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
        await use_case.execute(ExecutorRequest.model_validate(command), command["run_id"])
    with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
        await use_case.execute(ExecutorRequest.model_validate(command), command["run_id"])
    assert effect == ["started"]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS[:1], indirect=True)
async def test_native_input_size_denied_before_dispatch(owner_client):
    client, module, handler, command = owner_client
    command["input"]["content"] = "x" * 1000001
    response = await client.post("/api/v1/executor/requests", json=command, headers=_HEADERS)
    assert response.status_code == 413
    assert handler.await_count == 0
    assert await module.executor_ledger.lookup(command["company_id"], command["run_id"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS[:1], indirect=True)
@pytest.mark.parametrize(
    "result", [{"data": "x" * 1000001}, {"value": float("nan")}], ids=["oversized", "nonfinite"]
)
async def test_native_invalid_output_preserves_uncertainty_and_blocks_replay(owner_client, result):
    client, module, handler, command = owner_client
    handler.return_value = result
    response = await client.post("/api/v1/executor/requests", json=command, headers=_HEADERS)
    assert response.status_code == 503
    assert (
        await module.executor_ledger.lookup(command["company_id"], command["run_id"])
    ).state == "uncertain"
    assert (
        await client.post("/api/v1/executor/requests", json=command, headers=_HEADERS)
    ).status_code == 503
    assert handler.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_client", OWNERS[:1], indirect=True)
async def test_native_receipt_write_failure_and_cancellation_do_not_repeat_effects(
    owner_client, monkeypatch
):
    _, module, handler, command = owner_client
    effects = []

    async def effect(_):
        effects.append("done")
        return {"status": "ok"}

    async def failed_complete(*_):
        raise RuntimeError("receipt commit outcome unknown")

    monkeypatch.setattr(module.executor_ledger, "complete", failed_complete)
    use_case = NativeExecutorUseCase(
        module.executor_ledger,
        effect,
        runtime_id="requirement-manager",
        company_id=command["company_id"],
        allowed_actions=frozenset({"ingest"}),
    )
    with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
        await use_case.execute(ExecutorRequest.model_validate(command), command["run_id"])
    with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
        await use_case.execute(ExecutorRequest.model_validate(command), command["run_id"])
    assert effects == ["done"]

    # A cancelled owner keeps its committed intent even though no receipt exists.
    entered = asyncio.Event()

    async def interrupted(_):
        effects.append("started")
        entered.set()
        await asyncio.sleep(10)
        return {}

    next_command = ExecutorRequest.model_validate({**command, "run_id": "run-cancelled"})
    cancelled_case = NativeExecutorUseCase(
        module.executor_ledger,
        interrupted,
        runtime_id="requirement-manager",
        company_id=command["company_id"],
        allowed_actions=frozenset({"ingest"}),
    )
    task = asyncio.create_task(cancelled_case.execute(next_command, next_command.run_id))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        await module.executor_ledger.lookup(next_command.company_id, next_command.run_id)
    ).state == "uncertain"
    with pytest.raises(NativeExecutorError, match="executor_effects_uncertain"):
        await cancelled_case.execute(next_command, next_command.run_id)
    assert effects == ["done", "started"]
