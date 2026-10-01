"""Unit coverage for confirmed requirement delivery handoff boundaries."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from agents.requirement_manager.adapters.delivery_context import HttpDeliveryContextVerifier
from agents.requirement_manager.core.delivery_handoff import DeliveryHandoffUseCase
from agents.requirement_manager.core.domain.delivery_handoff import (
    ConfirmedRequirementSnapshot,
    DeliveryHandoffCommand,
)


def _snapshot(
    *,
    requirement_id: str = "req_unit_delivery",
    title: str = "Reviewed request",
    description: str = "Preserve the confirmed review evidence.",
    status: str = "confirmed",
    confirmed_by: str | None = "reviewer",
) -> ConfirmedRequirementSnapshot:
    return ConfirmedRequirementSnapshot(
        requirement_id, title, description, status, confirmed_by
    )


def _command(
    snapshot: ConfirmedRequirementSnapshot | None = None,
    **updates: object,
) -> DeliveryHandoffCommand:
    reviewed = snapshot or _snapshot()
    command = DeliveryHandoffCommand(
        company_id="cmp_delivery_unit",
        project_id=17,
        wp_id=21,
        goal_id="goal_reviewed",
        work_item_id="work_reviewed",
        requirement_hash=reviewed.content_hash,
        reason="Reviewed and approved for decomposition.",
        project_name="Synthetic project",
    )
    return command.model_copy(update=updates)


class _MemoryStore:
    def __init__(self, snapshots: dict[str, ConfirmedRequirementSnapshot]):
        self.snapshots = snapshots
        self.receipts = {}
        self.events = []

    @asynccontextmanager
    async def transaction(self):
        yield _MemoryTransaction(self)


class _MemoryTransaction:
    def __init__(self, store: _MemoryStore):
        self.store = store

    async def get_requirement(self, requirement_id: str):
        return self.store.snapshots.get(requirement_id)

    async def get_receipt(self, requirement_id: str):
        return self.store.receipts.get(requirement_id)

    async def save(self, receipt, event) -> None:
        self.store.receipts[receipt.requirement_id] = receipt
        self.store.events.append(event)


class _Verifier:
    def __init__(self, error: str | None = None):
        self.error = error
        self.calls = 0

    async def verify(self, command: DeliveryHandoffCommand) -> None:
        self.calls += 1
        if self.error:
            raise ValueError(self.error)


@pytest.mark.asyncio
async def test_review_exposes_confirmed_snapshot_hash() -> None:
    snapshot = _snapshot()
    store = _MemoryStore({snapshot.requirement_id: snapshot})
    use_case = DeliveryHandoffUseCase(store, company_id="cmp_delivery_unit", context_verifier=_Verifier())

    review = await use_case.review(snapshot.requirement_id)

    assert review.requirement_hash == snapshot.content_hash
    assert review.status == "confirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot", "error"),
    [
        (_snapshot(status="pending", confirmed_by=None), "requirement_confirmation_required"),
        (_snapshot(title="Edited after review"), "requirement_review_snapshot_changed"),
    ],
)
async def test_changed_or_unconfirmed_requirement_does_not_verify_or_queue(
    snapshot: ConfirmedRequirementSnapshot,
    error: str,
) -> None:
    store = _MemoryStore({snapshot.requirement_id: snapshot})
    verifier = _Verifier()
    use_case = DeliveryHandoffUseCase(
        store, company_id="cmp_delivery_unit", context_verifier=verifier
    )

    with pytest.raises(ValueError, match=error):
        await use_case.execute(
            snapshot.requirement_id,
            _command(),
            reviewed_by="reviewer",
            idempotency_key=f"requirement-delivery:{snapshot.requirement_id}",
            trace_id="trace-unit",
        )

    assert verifier.calls == 0
    assert store.receipts == {}
    assert store.events == []


@pytest.mark.asyncio
async def test_company_and_goal_work_item_context_mismatch_fail_closed() -> None:
    snapshot = _snapshot()
    store = _MemoryStore({snapshot.requirement_id: snapshot})
    verifier = _Verifier("delivery_context_mismatch")
    use_case = DeliveryHandoffUseCase(
        store, company_id="cmp_delivery_unit", context_verifier=verifier
    )

    with pytest.raises(ValueError, match="handoff_company_mismatch"):
        await use_case.execute(
            snapshot.requirement_id,
            _command(company_id="cmp_foreign"),
            reviewed_by="reviewer",
            idempotency_key=f"requirement-delivery:{snapshot.requirement_id}",
            trace_id=None,
        )
    assert verifier.calls == 0

    with pytest.raises(ValueError, match="delivery_context_mismatch"):
        await use_case.execute(
            snapshot.requirement_id,
            _command(),
            reviewed_by="reviewer",
            idempotency_key=f"requirement-delivery:{snapshot.requirement_id}",
            trace_id=None,
        )
    assert verifier.calls == 1
    assert store.receipts == {}
    assert store.events == []


@pytest.mark.asyncio
async def test_http_verifier_uses_only_bounded_gets_and_sends_internal_key() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("goal_reviewed"):
            return httpx.Response(200, json={"company_id": "cmp_delivery_unit"})
        return httpx.Response(
            200,
            json={
                "company_id": "cmp_delivery_unit",
                "goal_id": "goal_reviewed",
                "status": "ready",
            },
        )

    verifier = HttpDeliveryContextVerifier(
        "http://control-plane.test/",
        authorization="operator-token",
        internal_key="internal-test-key",
        transport=httpx.MockTransport(respond),
    )
    await verifier.verify(_command())

    assert len(requests) == 2
    assert all(request.method == "GET" for request in requests)
    assert [request.url.path for request in requests] == [
        "/api/v1/control-plane/goals/goal_reviewed",
        "/api/v1/control-plane/work-items/work_reviewed",
    ]
    assert all(request.headers["X-Internal-Key"] == "internal-test-key" for request in requests)
    assert all(request.headers["X-Control-Plane-Operator-Token"] == "operator-token" for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["invalid_json", "unavailable"],
)
async def test_http_verifier_redacts_invalid_or_unavailable_responses(failure: str) -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if failure == "invalid_json":
            return httpx.Response(200, text="private-invalid-response")
        return httpx.Response(503, text="private-control-plane-secret")

    verifier = HttpDeliveryContextVerifier(
        "http://control-plane.test",
        authorization="operator-token",
        internal_key="internal-test-key",
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(ValueError, match="delivery_context_unavailable") as exc_info:
        await verifier.verify(_command())

    assert "private-" not in str(exc_info.value)
    # The adapter fetches both authorized resources before parsing or applying
    # the company/relationship checks; it does not retry either request.
    assert len(requests) == 2
    assert all(request.method == "GET" for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goal_data,work_data",
    [
        ({"company_id": "cmp_foreign"}, {"company_id": "cmp_delivery_unit", "goal_id": "goal_reviewed", "status": "ready"}),
        ({"company_id": "cmp_delivery_unit"}, {"company_id": "cmp_foreign", "goal_id": "goal_reviewed", "status": "ready"}),
        ({"company_id": "cmp_delivery_unit"}, {"company_id": "cmp_delivery_unit", "goal_id": "goal_other", "status": "ready"}),
        ({"company_id": "cmp_delivery_unit"}, {"company_id": "cmp_delivery_unit", "goal_id": "goal_reviewed", "status": "done"}),
    ],
)
async def test_http_verifier_rejects_foreign_or_unavailable_delivery_context(
    goal_data: dict,
    work_data: dict,
) -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("goal_reviewed"):
            return httpx.Response(200, json=goal_data)
        return httpx.Response(200, json=work_data)

    verifier = HttpDeliveryContextVerifier(
        "http://control-plane.test",
        authorization="operator-token",
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(ValueError, match="delivery_context_mismatch"):
        await verifier.verify(_command())
