"""CompanyContext aggregate root and tenant-boundary policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import CompanyContext as CompanyContextRecord
from .events import ControlPlaneDomainEvent
from .metadata import ControlPlaneMetadata


class InvalidCompanyContextError(ValueError):
    """Raised when a CompanyContext record violates tenant invariants."""


def clean_company_name(value: Any) -> str:
    """Return a required, normalized company display name."""
    cleaned = str(value or "").strip()
    if not cleaned:
        raise InvalidCompanyContextError("name_required")
    return cleaned


def clean_company_mission(value: Any) -> str:
    """Return normalized company mission text."""
    return str(value or "").strip()


@dataclass(frozen=True, slots=True)
class CompanyContextCreated(ControlPlaneDomainEvent):
    """PII-safe in-memory event raised when a company context is created."""

    company_id: str
    name_length: int
    mission_length: int
    metadata_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompanyContextUpdated(ControlPlaneDomainEvent):
    """PII-safe in-memory event raised when a company context is updated."""

    company_id: str
    name_changed: bool
    mission_changed: bool
    metadata_changed: bool
    name_length: int
    mission_length: int
    metadata_keys: tuple[str, ...]


@dataclass
class CompanyContext:
    """CompanyContext aggregate root for the operating-company boundary."""

    record: CompanyContextRecord
    _events: list[CompanyContextCreated | CompanyContextUpdated] = field(
        default_factory=list
    )

    @classmethod
    def for_creation(cls, record: CompanyContextRecord) -> CompanyContext:
        aggregate = cls(record=record)
        aggregate._normalize_record()
        return aggregate

    @classmethod
    def from_record(cls, record: CompanyContextRecord) -> CompanyContext:
        aggregate = cls(record=record)
        aggregate._normalize_record()
        return aggregate

    @property
    def company_id(self) -> str:
        return self.record.company_id

    def apply_update(
        self,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Apply a validated company-context update to the aggregate record."""
        update_values: dict[str, Any] = {}
        if name is not None:
            update_values["name"] = clean_company_name(name)
        if mission is not None:
            update_values["mission"] = clean_company_mission(mission)
        if metadata is not None:
            update_values["metadata"] = ControlPlaneMetadata.from_mapping(
                metadata
            ).as_dict()

        if update_values:
            self.record = self.record.model_copy(update=update_values)
            self._normalize_record()

        self._events.append(
            CompanyContextUpdated(
                company_id=self.company_id,
                name_changed=name is not None,
                mission_changed=mission is not None,
                metadata_changed=metadata is not None,
                name_length=len(self.record.name),
                mission_length=len(self.record.mission),
                metadata_keys=ControlPlaneMetadata.from_mapping(
                    self.record.metadata
                ).keys_tuple,
            )
        )

    def mark_created(self) -> None:
        """Raise the creation event after persistence has accepted the record."""
        self._events.append(
            CompanyContextCreated(
                company_id=self.company_id,
                name_length=len(self.record.name),
                mission_length=len(self.record.mission),
                metadata_keys=ControlPlaneMetadata.from_mapping(
                    self.record.metadata
                ).keys_tuple,
            )
        )

    def pull_events(self) -> list[CompanyContextCreated | CompanyContextUpdated]:
        """Drain raised domain events for audit/outbox collection."""
        drained = list(self._events)
        self._events.clear()
        return drained

    def _normalize_record(self) -> None:
        self.record = self.record.model_copy(
            update={
                "name": clean_company_name(self.record.name),
                "mission": clean_company_mission(self.record.mission),
                "metadata": ControlPlaneMetadata.from_mapping(
                    self.record.metadata
                ).as_dict(),
            }
        )


__all__ = [
    "CompanyContext",
    "CompanyContextCreated",
    "CompanyContextUpdated",
    "InvalidCompanyContextError",
    "clean_company_mission",
    "clean_company_name",
]
