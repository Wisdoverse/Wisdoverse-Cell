"""Ports for the Requirement Manager gRPC boundary."""

from typing import Any, Protocol


class RequirementGrpcStore(Protocol):
    """Read/write port used by the gRPC interface boundary."""

    async def get_many(self, requirement_ids: list[str]) -> list[Any]:
        """Return requirements by id, preserving the requested order when possible."""

    async def get_by_id(self, requirement_id: str) -> Any | None:
        """Return one requirement by id."""

    async def list_requirements(
        self,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        """Return a page of requirements and the total matching count."""

    async def search_requirements(
        self,
        *,
        keyword: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        """Return a page of requirements matching a keyword and the total count."""

    async def confirm(self, requirement_id: str, confirmed_by: str) -> Any | None:
        """Confirm one requirement."""

    async def reject(
        self,
        requirement_id: str,
        *,
        reason: str,
        rejected_by: str,
    ) -> Any | None:
        """Reject one requirement."""
