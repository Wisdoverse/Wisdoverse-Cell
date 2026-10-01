"""Requirement-to-Control-Plane handoff acceptance over isolated PostgreSQL."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.requirement_manager.adapters.delivery_context import HttpDeliveryContextVerifier
from agents.requirement_manager.api.delivery_handoff import (
    get_handoff_use_case,
)
from agents.requirement_manager.api.delivery_handoff import (
    router as delivery_handoff_router,
)
from agents.requirement_manager.core.delivery_handoff import DeliveryHandoffUseCase
from agents.requirement_manager.core.domain.delivery_handoff import (
    ConfirmedRequirementSnapshot,
)
from agents.requirement_manager.db.delivery_handoff import (
    RequirementDeliveryHandoffTable,
    SqlAlchemyDeliveryHandoffStore,
)
from agents.requirement_manager.models import Base as RequirementBase
from agents.requirement_manager.models import Requirement, RequirementEventOutbox
from shared.config import settings
from shared.control_plane.api import create_control_plane_router
from shared.control_plane.models import CompanyContext, Goal, WorkItem
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.tables import control_plane_metadata
from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.event import EventTypes

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _database() -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], str]]:
    if not DATABASE_URL.startswith(("postgresql+asyncpg://", "postgresql://")):
        pytest.skip("TEST_DATABASE_URL must provide disposable PostgreSQL")

    schema = "requirement_delivery_test_" + uuid4().hex
    admin = create_async_engine(DATABASE_URL)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
            await connection.run_sync(RequirementBase.metadata.create_all)
        yield sessions, schema
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _operator_token(monkeypatch, *, companies: list[str], scopes: list[str]) -> str:
    token = "synthetic-delivery-operator-token"
    monkeypatch.setattr(
        settings,
        "control_plane_operators_json",
        json.dumps(
            [
                {
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "actor_id": "synthetic-delivery-reviewer",
                    "companies": companies,
                    "scopes": scopes,
                }
            ]
        ),
    )
    return token


def _snapshot_hash(requirement_id: str, title: str, description: str) -> str:
    return ConfirmedRequirementSnapshot(
        requirement_id=requirement_id,
        title=title,
        description=description,
        status="confirmed",
        confirmed_by="synthetic-reviewer",
    ).content_hash


def _body(
    *,
    company_id: str,
    goal_id: str,
    work_item_id: str,
    requirement_hash: str,
    project_id: int = 71,
    wp_id: int = 902,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "company_id": company_id,
        "project_id": project_id,
        "wp_id": wp_id,
        "goal_id": goal_id,
        "work_item_id": work_item_id,
        "requirement_hash": requirement_hash,
        "reason": "Reviewed confirmed requirement and approved this synthetic handoff.",
        "project_name": "Synthetic delivery project",
    }


async def test_confirmed_requirement_handoff_is_atomic_idempotent_and_context_verified(
    monkeypatch,
):
    async with _database() as (sessions, schema):
        company_id = "cmp_delivery_handoff"
        requirement_id = "req_delivery_handoff_1"
        monkeypatch.setattr(settings, "control_plane_company_id", company_id)
        monkeypatch.setattr(settings, "internal_service_key", "synthetic-internal-key")
        token = _operator_token(
            monkeypatch,
            companies=[company_id, "cmp_delivery_other"],
            scopes=["work:execute", "control-plane:read"],
        )
        async with sessions() as session:
            stores = ControlPlaneStores(session)
            await stores.companies.create_company(
                CompanyContext(company_id=company_id, name="Synthetic Delivery")
            )
            goal = await stores.goals.create_goal(
                Goal(company_id=company_id, title="Deliver reviewed requirement")
            )
            work_item = await stores.work_items.create_work_item(
                WorkItem(
                    company_id=company_id,
                    title="Implement reviewed requirement",
                    goal_id=goal.goal_id,
                )
            )
            unrelated_goal = await stores.goals.create_goal(
                Goal(company_id=company_id, title="Unrelated synthetic goal")
            )
            unrelated_work_item = await stores.work_items.create_work_item(
                WorkItem(
                    company_id=company_id,
                    title="Work linked to unrelated goal",
                    goal_id=unrelated_goal.goal_id,
                )
            )
            session.add(
                Requirement(
                    id=requirement_id,
                    title="Add a reviewed export",
                    description="The export must preserve company scope and review evidence.",
                    status="confirmed",
                    confirmed_by="synthetic-reviewer",
                )
            )
            session.add(
                Requirement(
                    id="req_delivery_pending",
                    title="Unconfirmed request",
                    description="This has not been confirmed.",
                    status="pending",
                )
            )
            session.add(
                Requirement(
                    id="req_delivery_changed",
                    title="Changed after review",
                    description="The current snapshot differs from review.",
                    status="confirmed",
                    confirmed_by="synthetic-reviewer",
                )
            )
            session.add(
                Requirement(
                    id="req_delivery_foreign_context",
                    title="Foreign context request",
                    description="This must not map to a foreign company object.",
                    status="confirmed",
                    confirmed_by="synthetic-reviewer",
                )
            )
            session.add(
                Requirement(
                    id="req_delivery_duplicate_wp",
                    title="A second confirmed request",
                    description="A distinct request cannot claim an already mapped work package.",
                    status="confirmed",
                    confirmed_by="synthetic-reviewer",
                )
            )
            await session.commit()

        app = FastAPI()
        app.include_router(
            create_control_plane_router(session_provider=_session_provider(sessions)),
            dependencies=[Depends(verify_internal_key)],
        )
        app.include_router(
            delivery_handoff_router, dependencies=[Depends(verify_internal_key)]
        )
        observed_requests: list[tuple[str, str, int]] = []

        @app.middleware("http")
        async def observe_control_plane_reads(request, call_next):
            response = await call_next(request)
            if request.url.path.startswith("/api/v1/control-plane/"):
                observed_requests.append((request.method, request.url.path, response.status_code))
            return response

        transport = ASGITransport(app=app)

        async def provide_handoff_use_case(request: Request):
            return DeliveryHandoffUseCase(
                SqlAlchemyDeliveryHandoffStore(sessions),
                company_id=company_id,
                context_verifier=HttpDeliveryContextVerifier(
                    "http://control-plane.test",
                    authorization=request.headers.get("X-Control-Plane-Operator-Token", ""),
                    internal_key=settings.internal_service_key,
                    transport=ASGITransport(app=app),
                ),
            )

        app.dependency_overrides[get_handoff_use_case] = provide_handoff_use_case
        headers = {
            "X-Control-Plane-Operator-Token": token,
            "Idempotency-Key": f"requirement-delivery:{requirement_id}",
            "X-Trace-ID": "trace-synthetic-delivery-handoff",
            "X-Internal-Key": settings.internal_service_key,
        }
        primary_body = _body(
            company_id=company_id,
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            requirement_hash=_snapshot_hash(
                requirement_id,
                "Add a reviewed export",
                "The export must preserve company scope and review evidence.",
            ),
        )

        async with AsyncClient(transport=transport, base_url="http://cell.test") as client:
            review = await client.get(
                f"/api/v1/requirements/{requirement_id}/delivery-review",
                headers=headers,
            )
            assert review.status_code == 200
            assert review.json()["requirement_hash"] == primary_body["requirement_hash"]
            assert review.json()["status"] == "confirmed"
            overlong_id = await client.get(
                f"/api/v1/requirements/{'r' * 33}/delivery-review",
                headers=headers,
            )
            assert overlong_id.status_code == 422
            overlong_trace = await client.post(
                f"/api/v1/requirements/{requirement_id}/delivery-handoff",
                headers={**headers, "X-Trace-ID": "t" * 65},
                json=primary_body,
            )
            assert overlong_trace.status_code == 422

            # Competing requests exercise the row lock and immutable replay behavior.
            first, second = await asyncio.gather(
                client.post(
                    f"/api/v1/requirements/{requirement_id}/delivery-handoff",
                    headers=headers,
                    json=primary_body,
                ),
                client.post(
                    f"/api/v1/requirements/{requirement_id}/delivery-handoff",
                    headers=headers,
                    json=primary_body,
                ),
            )
            assert first.status_code == second.status_code == 200, (
                first.text,
                second.text,
                observed_requests,
            )
            receipt = first.json()
            assert second.json() == receipt
            assert receipt["status"] == "queued_for_decomposition"
            assert receipt["reviewed_by"] == "synthetic-delivery-reviewer"
            assert receipt["review_reason"] == primary_body["reason"]
            assert receipt["requirement_hash"] == primary_body["requirement_hash"]
            assert receipt["company_id"] == company_id
            assert receipt["goal_id"] == goal.goal_id
            assert receipt["work_item_id"] == work_item.work_item_id

            # A fresh session models process restart and reads the committed receipt/outbox.
            async with sessions() as restarted_session:
                persisted = await restarted_session.get(
                    RequirementDeliveryHandoffTable, requirement_id
                )
                outbox_rows = list(
                    (
                        await restarted_session.scalars(
                            select(RequirementEventOutbox).where(
                                RequirementEventOutbox.event_type
                                == EventTypes.SYNC_TASK_NEEDS_DECOMPOSE
                            )
                        )
                    ).all()
                )
                assert persisted is not None
                assert persisted.receipt["event_id"] == receipt["event_id"]
                assert len(outbox_rows) == 1
                event = outbox_rows[0]
                assert event.event_id == receipt["event_id"]
                assert event.status == "pending"
                assert event.trace_id == "trace-synthetic-delivery-handoff"
                assert event.correlation_id == requirement_id
                assert event.payload["wp_id"] == primary_body["wp_id"]
                assert event.payload["project_id"] == primary_body["project_id"]
                assert event.payload["goal_id"] == goal.goal_id
                assert event.payload["work_item_id"] == work_item.work_item_id
                assert event.payload["requirement_id"] == requirement_id
            assert all(method == "GET" for method, _, _ in observed_requests)
            assert all(status == 200 for _, _, status in observed_requests)
            assert len(observed_requests) == 2

            changed_body = dict(primary_body)
            changed_body["wp_id"] = 903
            conflict = await client.post(
                f"/api/v1/requirements/{requirement_id}/delivery-handoff",
                headers=headers,
                json=changed_body,
            )
            assert conflict.status_code == 409
            assert conflict.json()["detail"] == "handoff_mapping_conflict"

            duplicate_wp_body = _body(
                company_id=company_id,
                goal_id=goal.goal_id,
                work_item_id=work_item.work_item_id,
                requirement_hash=_snapshot_hash(
                    "req_delivery_duplicate_wp",
                    "A second confirmed request",
                    "A distinct request cannot claim an already mapped work package.",
                ),
            )
            duplicate_wp = await client.post(
                "/api/v1/requirements/req_delivery_duplicate_wp/delivery-handoff",
                headers={
                    **headers,
                    "Idempotency-Key": "requirement-delivery:req_delivery_duplicate_wp",
                },
                json=duplicate_wp_body,
            )
            assert duplicate_wp.status_code == 409
            assert duplicate_wp.json()["detail"] == "handoff_work_package_already_mapped"

            pending_body = _body(
                company_id=company_id,
                goal_id=goal.goal_id,
                work_item_id=work_item.work_item_id,
                requirement_hash=_snapshot_hash(
                    "req_delivery_pending", "Unconfirmed request", "This has not been confirmed."
                ),
            )
            pending = await client.post(
                "/api/v1/requirements/req_delivery_pending/delivery-handoff",
                headers={
                    **headers,
                    "Idempotency-Key": "requirement-delivery:req_delivery_pending",
                },
                json=pending_body,
            )
            assert pending.status_code == 409
            assert pending.json()["detail"] == "requirement_confirmation_required"

            changed_requirement_body = _body(
                company_id=company_id,
                goal_id=goal.goal_id,
                work_item_id=work_item.work_item_id,
                requirement_hash=_snapshot_hash(
                    "req_delivery_changed",
                    "Changed after review",
                    "The current snapshot differs from review.",
                ),
            )
            async with sessions() as session:
                changed_row = await session.get(Requirement, "req_delivery_changed")
                assert changed_row is not None
                changed_row.title = "Edited after confirmation"
                await session.commit()
            changed_snapshot = await client.post(
                "/api/v1/requirements/req_delivery_changed/delivery-handoff",
                headers={
                    **headers,
                    "Idempotency-Key": "requirement-delivery:req_delivery_changed",
                },
                json=changed_requirement_body,
            )
            assert changed_snapshot.status_code == 409
            assert changed_snapshot.json()["detail"] == "requirement_review_snapshot_changed"

            mismatch_body = dict(primary_body)
            mismatch_body["company_id"] = "cmp_delivery_other"
            mismatch = await client.post(
                f"/api/v1/requirements/{requirement_id}/delivery-handoff",
                headers=headers,
                json=mismatch_body,
            )
            assert mismatch.status_code == 409
            assert mismatch.json()["detail"] == "handoff_company_mismatch"

            bad_idempotency = await client.post(
                "/api/v1/requirements/req_delivery_pending/delivery-handoff",
                headers={**headers, "Idempotency-Key": "wrong-key"},
                json=pending_body,
            )
            assert bad_idempotency.status_code == 409
            assert bad_idempotency.json()["detail"] == ("handoff_idempotency_or_actor_invalid")

            bad_hash = dict(primary_body)
            bad_hash["requirement_hash"] = "not-a-sha256"
            invalid_contract = await client.post(
                f"/api/v1/requirements/{requirement_id}/delivery-handoff",
                headers=headers,
                json=bad_hash,
            )
            assert invalid_contract.status_code == 422

            relationship_mismatch_body = _body(
                company_id=company_id,
                goal_id=goal.goal_id,
                work_item_id=unrelated_work_item.work_item_id,
                requirement_hash=_snapshot_hash(
                    "req_delivery_foreign_context",
                    "Foreign context request",
                    "This must not map to a foreign company object.",
                ),
            )
            relationship_mismatch = await client.post(
                "/api/v1/requirements/req_delivery_foreign_context/delivery-handoff",
                headers={
                    **headers,
                    "Idempotency-Key": "requirement-delivery:req_delivery_foreign_context",
                },
                json=relationship_mismatch_body,
            )
            assert relationship_mismatch.status_code == 409
            assert relationship_mismatch.json()["detail"] == "delivery_context_mismatch"

            denied_token = _operator_token(
                monkeypatch,
                companies=[company_id],
                scopes=["control-plane:read"],
            )
            denied = await client.post(
                "/api/v1/requirements/req_delivery_pending/delivery-handoff",
                headers={
                    **headers,
                    "X-Control-Plane-Operator-Token": denied_token,
                    "Idempotency-Key": "requirement-delivery:req_delivery_pending",
                },
                json=pending_body,
            )
            assert denied.status_code == 403

        async with sessions() as final_session:
            mapped = await final_session.get(RequirementDeliveryHandoffTable, requirement_id)
            all_outbox = list((await final_session.scalars(select(RequirementEventOutbox))).all())
            assert mapped is not None
            assert len(all_outbox) == 1
            assert await final_session.get(
                RequirementDeliveryHandoffTable, "req_delivery_duplicate_wp"
            ) is None


def _session_provider(sessions):
    @asynccontextmanager
    async def provider():
        async with sessions() as session:
            yield session
            await session.flush()

    return provider
