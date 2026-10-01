"""Privileged API and SQL paging coverage for audit export."""

import hashlib
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.control_plane.api_routes.audit_export import create_audit_export_router
from shared.control_plane.audit_export_store import (
    AuditExportCursorError,
    SqlAlchemyAuditExportStore,
)
from shared.control_plane.tables import AuditEventTable


class _CountingExportStore:
    def __init__(self, session: AsyncSession):
        self._store = SqlAlchemyAuditExportStore(session)
        self.calls = 0

    async def list_page(self, **kwargs):
        self.calls += 1
        return await self._store.list_page(**kwargs)


def _configure_operator(
    monkeypatch, *, actor_id: str, companies: list[str], scopes: list[str]
) -> str:
    token = f"audit-export-{actor_id}"
    entry = {
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "actor_id": actor_id,
        "companies": companies,
        "scopes": scopes,
    }
    monkeypatch.setattr(settings, "control_plane_operators_json", json.dumps([entry]))
    return token


async def _seed_events(
    session: AsyncSession, *, company_id: str, ids: list[str], created_at: datetime
) -> None:
    for event_id in ids:
        session.add(
            AuditEventTable(
                audit_event_id=event_id,
                company_id=company_id,
                action="artifact.created",
                target_type="artifact",
                target_id=f"art_{event_id}",
                actor_type="operator",
                actor_id="operator_link_1",
                detail={
                    "artifact_id": f"art_{event_id}",
                    "content_hash": "sha256:preserve-linkage",
                    "authorization": "Bearer abcdefghijklmnop",
                    "api_token": "private-token-value",
                    "request_body": {"customer_email": "pii@example.test"},
                    "status": "succeeded",
                },
                created_at=created_at,
            )
        )
    await session.flush()


def _router(counting_store: _CountingExportStore):
    async def get_stores() -> AsyncGenerator[object, None]:
        yield type("Stores", (), {"audit_export": counting_store})()

    app = FastAPI()
    app.include_router(
        create_audit_export_router(get_stores=get_stores), prefix="/api/v1/control-plane"
    )
    return app


@pytest.mark.asyncio
async def test_export_pages_stably_for_equal_timestamps_and_redacts_without_mutating_rows(
    db_session, monkeypatch
):
    company = "cmp_export_a"
    timestamp = datetime.now(UTC) - timedelta(minutes=1)
    ids = [f"audit_export_{index:02d}" for index in range(5)]
    await _seed_events(db_session, company_id=company, ids=ids, created_at=timestamp)
    await _seed_events(
        db_session, company_id="cmp_export_b", ids=["audit_export_foreign"], created_at=timestamp
    )
    await db_session.commit()

    token = _configure_operator(
        monkeypatch, actor_id="operator-a", companies=[company], scopes=["audit:export"]
    )
    counting_store = _CountingExportStore(db_session)
    app = _router(counting_store)
    start = (timestamp - timedelta(hours=1)).isoformat()
    end = datetime.now(UTC).isoformat()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page1 = await client.get(
            "/api/v1/control-plane/audit-export",
            headers={
                "X-Control-Plane-Operator-Token": token,
            },
            params={"company_id": company, "since": start, "until": end, "limit": 2},
        )
        assert page1.status_code == 200, page1.text
        body1 = page1.json()
        assert [event["audit_event_id"] for event in body1["audit_events"]] == ids[:2]
        assert body1["next_cursor"] == ids[1]
        exported_text = page1.text
        for secret in ("abcdefghijklmnop", "private-token-value", "pii@example.test"):
            assert secret not in exported_text
        assert body1["audit_events"][0]["detail"]["content_hash"] == "sha256:preserve-linkage"
        assert body1["audit_events"][0]["detail"]["artifact_id"] == f"art_{ids[0]}"

        page2 = await client.get(
            "/api/v1/control-plane/audit-export",
            headers={
                "X-Control-Plane-Operator-Token": token,
            },
            params={
                "company_id": company,
                "since": start,
                "until": end,
                "after_id": body1["next_cursor"],
                "limit": 2,
            },
        )
        assert page2.status_code == 200, page2.text
        body2 = page2.json()
        assert [event["audit_event_id"] for event in body2["audit_events"]] == ids[2:4]
        assert body2["next_cursor"] == ids[3]

        page3 = await client.get(
            "/api/v1/control-plane/audit-export",
            headers={
                "X-Control-Plane-Operator-Token": token,
            },
            params={
                "company_id": company,
                "since": start,
                "until": end,
                "after_id": body2["next_cursor"],
                "limit": 2,
            },
        )
        assert page3.status_code == 200
        assert [event["audit_event_id"] for event in page3.json()["audit_events"]] == ids[4:]
        assert page3.json()["next_cursor"] is None

    stored = (
        await db_session.execute(
            select(AuditEventTable).where(
                AuditEventTable.audit_event_id == ids[0],
            )
        )
    ).scalar_one()
    assert stored.detail["api_token"] == "private-token-value"
    assert stored.detail["request_body"]["customer_email"] == "pii@example.test"
    assert counting_store.calls == 3


@pytest.mark.asyncio
async def test_export_requires_company_scope_and_blocks_old_ranges_before_database_query(
    db_session, monkeypatch
):
    timestamp = datetime.now(UTC) - timedelta(minutes=1)
    await _seed_events(
        db_session, company_id="cmp_export_a", ids=["audit_export_a"], created_at=timestamp
    )
    await _seed_events(
        db_session, company_id="cmp_export_b", ids=["audit_export_b"], created_at=timestamp
    )
    await db_session.commit()
    token = _configure_operator(
        monkeypatch, actor_id="operator-b", companies=["cmp_export_b"], scopes=["audit:export"]
    )
    counting_store = _CountingExportStore(db_session)
    app = _router(counting_store)
    start = (timestamp - timedelta(hours=1)).isoformat()
    end = datetime.now(UTC).isoformat()
    old = datetime.now(UTC) - timedelta(days=91)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cross_company = await client.get(
            "/api/v1/control-plane/audit-export",
            headers={
                "X-Control-Plane-Operator-Token": token,
            },
            params={"company_id": "cmp_export_a", "since": start, "until": end},
        )
        assert cross_company.status_code == 403

        blocked_old_range = await client.get(
            "/api/v1/control-plane/audit-export",
            headers={
                "X-Control-Plane-Operator-Token": token,
            },
            params={"company_id": "cmp_export_b", "since": old.isoformat(), "until": end},
        )
        assert blocked_old_range.status_code == 400
        assert "outside_retention" in blocked_old_range.text

        own_company = await client.get(
            "/api/v1/control-plane/audit-export",
            headers={
                "X-Control-Plane-Operator-Token": token,
            },
            params={"company_id": "cmp_export_b", "since": start, "until": end},
        )
        assert own_company.status_code == 200
        assert [event["audit_event_id"] for event in own_company.json()["audit_events"]] == [
            "audit_export_b"
        ]

    assert counting_store.calls == 1


@pytest.mark.asyncio
async def test_store_rejects_cursor_from_another_company(db_session):
    timestamp = datetime.now(UTC)
    await _seed_events(
        db_session, company_id="cmp_export_a", ids=["audit_export_a"], created_at=timestamp
    )
    await _seed_events(
        db_session, company_id="cmp_export_b", ids=["audit_export_b"], created_at=timestamp
    )
    await db_session.commit()
    store = SqlAlchemyAuditExportStore(db_session)

    with pytest.raises(AuditExportCursorError, match="cursor_invalid"):
        await store.list_page(
            company_id="cmp_export_a",
            since=timestamp - timedelta(seconds=1),
            until=timestamp + timedelta(seconds=1),
            after_id="audit_export_b",
            limit=2,
        )
