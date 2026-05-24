"""Identity event outbox store tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.db.identity_event_outbox_store import SqlAlchemyIdentityEventOutboxStore
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_identity_event_outbox_store_add_preserves_event_contract() -> None:
    """The SQLAlchemy adapter stores the immutable event envelope."""
    session = MagicMock()
    session.flush = AsyncMock()
    store = SqlAlchemyIdentityEventOutboxStore(session)
    event = Event.create(
        event_type=EventTypes.IDENTITY_USER_CREATED,
        source_agent="identity-user",
        payload={
            "user_id": "usr_01identity",
            "domain_event": "UserCreated",
            "occurred_at": "2026-05-23T00:00:00+00:00",
            "email_present": True,
            "phone_present": False,
        },
        trace_id="trace-identity",
    )

    await store.add(event)

    row = session.add.call_args.args[0]
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.IDENTITY_USER_CREATED
    assert row.source_agent == "identity-user"
    assert row.payload["user_id"] == "usr_01identity"
    assert row.trace_id == "trace-identity"
    assert row.status == "pending"
