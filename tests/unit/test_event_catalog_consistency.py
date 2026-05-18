"""Event catalog ↔ code consistency tests.

Stage 5 (engineering quality) testing piece. These tests are
intentionally narrow: they catch the worst regressions (catalog
gone, payload module emptied, schema_version gone) without coupling
to the exact one-to-one mapping between catalog rows and Pydantic
classes, which is intentionally many-to-one in places.

Three rules enforced here:

1. The Event Catalog at docs/guides/event-catalog.md is non-empty
   and references the runtime `EventTypes` contract.
2. shared/schemas/event_payloads.py declares at least 50 Pydantic
   payload classes (regression guard against accidental deletion).
3. Every documented Pydantic event-envelope field still appears on
   the Event class declaration (catches `schema_version` /
   `event_id` / `metadata` removal).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import shared.schemas.event_payloads as event_payloads_module
from shared.schemas.event import Event, EventTypes

CATALOG_PATH = Path("docs/guides/event-catalog.md")
GUIDELINES_PATH = Path("docs/architecture/event-guidelines.md")


def _payload_model_class_names() -> set[str]:
    """Return Pydantic payload class names declared in event_payloads."""
    classes: set[str] = set()
    for name, obj in inspect.getmembers(event_payloads_module, inspect.isclass):
        if obj.__module__ != event_payloads_module.__name__:
            continue
        if name.startswith("_") or name == "Event":
            continue
        if "Payload" not in name:
            continue
        classes.add(name)
    return classes


def test_event_catalog_file_is_present_and_documents_the_contract() -> None:
    """Catalog exists and references the runtime contract entry points.

    Guards against the catalog being deleted, renamed, or losing its
    cross-link to the binding `event_id` / `schema_version` envelope.
    """
    assert CATALOG_PATH.exists(), "docs/guides/event-catalog.md is missing"
    text = CATALOG_PATH.read_text()
    assert "Event Contract" in text or "Event Catalog" in text
    assert "event_id" in text
    assert "schema_version" in text
    # `event_type` is the canonical envelope key.
    assert re.search(r"event_type\s*=\s*['\"]\{?domain\}?", text)


def test_event_payloads_module_has_payload_classes() -> None:
    """Smoke check: at least 50 payload classes are declared.

    Guards against accidental mass-deletion of the payload contract
    module.
    """
    payload_classes = _payload_model_class_names()
    assert len(payload_classes) >= 50, (
        f"Expected at least 50 payload classes in "
        f"shared/schemas/event_payloads.py, found {len(payload_classes)}"
    )


def test_event_envelope_keeps_required_fields() -> None:
    """The runtime Event class keeps the envelope fields documented in
    the catalog and event-guidelines.

    Catches accidental field removal that would break the public
    integration contract.
    """
    field_names = set(Event.model_fields.keys())
    required = {"event_id", "event_type", "source_agent", "payload", "schema_version"}
    missing = required - field_names
    assert not missing, (
        f"Event envelope is missing required fields: {sorted(missing)}. "
        "Restore them or update docs/architecture/event-guidelines.md "
        "and docs/guides/event-catalog.md to reflect the change."
    )


def test_event_types_class_has_active_constants() -> None:
    """`EventTypes` still declares the canonical event-type constants.

    Guards against accidental empty class or rename.
    """
    constants = {
        k: v
        for k, v in vars(EventTypes).items()
        if not k.startswith("_") and isinstance(v, str)
    }
    assert len(constants) >= 50, (
        f"Expected at least 50 EventTypes constants; found {len(constants)}"
    )
    # Spot-check a handful that the documentation depends on.
    for spot in (
        "requirement.extracted",
        "qa.acceptance-completed",
        "sync.completed",
        "agent_run.started",
        "agent_run.succeeded",
        "agent_run.failed",
    ):
        assert spot in set(constants.values()), (
            f"Expected EventTypes constant with value {spot!r}; "
            "the Event Catalog and idempotency contract reference it."
        )


def test_event_guidelines_references_outbox_pattern() -> None:
    """Event Guidelines document the outbox-as-publish path.

    Guards against the foundation doc losing its core rule that
    producers stage events in the outbox rather than publishing
    directly to the EventBus.
    """
    assert GUIDELINES_PATH.exists()
    text = GUIDELINES_PATH.read_text()
    assert "outbox" in text.lower(), (
        "event-guidelines.md must document the outbox-as-publish rule"
    )
    assert "Idempoten" in text or "idempoten" in text, (
        "event-guidelines.md must document the idempotency rule"
    )
