"""Typed OpenProject record shapes (DDD-013 / DDD-022 follow-up).

Replaces the bare `list[dict[str, Any]]` return types on
`OpenProjectWorkPackagePort` with `TypedDict` records so mypy can
catch field-name typos at the port boundary without changing the
runtime shape (a TypedDict IS a dict at runtime, so all existing
`wp.get("field")` / `wp["field"]` call sites keep working).

Per `architecture-principles.md` §4.6 (Anti-Corruption Layer rule):
external-system shapes belong to the integration boundary, not the
caller. These records are the typed surface every caller sees;
adapters validate / project upstream responses into them before
returning.

`total=False` on every TypedDict reflects OpenProject's reality:
the HAL+JSON payload often omits optional fields. Callers should
keep defending against `None` via `.get(field, default)` instead
of trusting presence.
"""

from __future__ import annotations

from typing import Any, TypedDict


class OpenProjectLinkRef(TypedDict, total=False):
    """One link entry inside an OpenProject `_links` object."""

    href: str
    title: str


class OpenProjectLinks(TypedDict, total=False):
    """The `_links` subobject on a work package.

    Open-ended on purpose — OpenProject ships many link kinds and
    only the ones consumed by our callers are enumerated here.
    """

    parent: OpenProjectLinkRef
    project: OpenProjectLinkRef
    status: OpenProjectLinkRef
    type: OpenProjectLinkRef
    assignee: OpenProjectLinkRef
    assignedTo: OpenProjectLinkRef


class OpenProjectDescription(TypedDict, total=False):
    """The `description` subobject on a work package."""

    raw: str
    format: str
    html: str


class OpenProjectWorkPackage(TypedDict, total=False):
    """Typed OpenProject work-package record.

    All fields are optional (`total=False`) because OpenProject's
    HAL payload routinely omits keys; callers must continue to
    use `.get(field, default)` and not trust presence.
    """

    id: int
    subject: str
    description: OpenProjectDescription
    percentageDone: int
    dueDate: str
    updatedAt: str
    createdAt: str
    _links: OpenProjectLinks
    # `Any`-typed escape hatch for fields not yet promoted; keeping
    # this avoids breaking callers that read OpenProject extras
    # before we surface them as typed keys.
    _extras: dict[str, Any]
