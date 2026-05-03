"""Port interfaces for external platform integrations.

Application and domain services depend on these protocols. Concrete adapters
live under ``shared.integrations`` and are wired at service entry points.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OpenProjectWorkPackagePort(Protocol):
    """OpenProject work-package operations used by agents and capabilities."""

    async def get_work_packages(
        self,
        project_id: int | None = None,
        filters: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Return work packages visible to the configured integration user."""

    async def get_work_package(self, wp_id: int) -> dict[str, Any]:
        """Return one work package by OpenProject ID."""

    async def update_work_package(
        self,
        wp_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update one work package and return the updated representation."""

    async def create_work_package(
        self,
        project_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a work package inside an OpenProject project."""

    async def close(self) -> None:
        """Release adapter resources."""


@runtime_checkable
class BitableTablePort(Protocol):
    """Feishu Bitable table operations used through a platform adapter."""

    async def list_records(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        """Return one page of records."""

    async def list_all_records(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all records by following pagination."""

    async def create_record(
        self,
        fields: dict[str, Any],
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> str:
        """Create a record and return its external record ID."""

    async def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> bool:
        """Update a record by external record ID."""

    async def list_fields(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return table field metadata."""

    async def create_field(
        self,
        field_name: str,
        field_type: int = 1,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a table field and return adapter-specific metadata."""


@runtime_checkable
class FeishuMessengerPort(Protocol):
    """Messaging operations used by services that notify Feishu."""

    async def send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: str,
    ) -> dict[str, Any] | None:
        """Send a message to Feishu."""

    async def send_card(
        self,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Send an interactive card to Feishu."""


@runtime_checkable
class FeishuContactLookupPort(Protocol):
    """Feishu contact lookup operations used by user-facing gateways."""

    async def lookup_user_ids(
        self,
        *,
        emails: list[str] | None = None,
        mobiles: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Resolve emails or mobile numbers into Feishu open IDs."""


@runtime_checkable
class FeishuWebhookPort(Protocol):
    """Feishu webhook operations used by notification fan-out services."""

    async def send_interactive_card(
        self,
        *,
        webhook_url: str,
        card: dict[str, Any],
    ) -> bool:
        """Send an interactive card through a Feishu webhook URL."""


@runtime_checkable
class GitLabMergeRequestNotePort(Protocol):
    """GitLab merge-request note operations used by QA reporting."""

    async def upsert_mr_note(
        self,
        mr_iid: int,
        body: str,
        *,
        project_id: str | None = None,
    ) -> bool:
        """Create or update an MR note and return whether it succeeded."""


@runtime_checkable
class GitLabMergeRequestPort(Protocol):
    """GitLab merge-request operations used by development workflows."""

    async def check_existing_mr(self, source_branch: str) -> dict[str, Any] | None:
        """Return an open MR for the source branch, if one exists."""

    async def create_mr(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a merge request and return its external representation."""
