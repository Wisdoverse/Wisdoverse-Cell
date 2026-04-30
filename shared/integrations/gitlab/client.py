"""GitLab API client for MR note operations.

Used by QA Agent to post/update acceptance reports on merge requests.
Supports marker-based upsert to avoid duplicate comments.
"""

from __future__ import annotations

import httpx

from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger("integrations.gitlab")


class GitLabClient:
    """Async GitLab API client for MR note management."""

    def __init__(
        self,
        api_url: str | None = None,
        project_id: str | None = None,
        token: str | None = None,
        comment_marker: str | None = None,
    ):
        self._api_url = (api_url or settings.gitlab_api_url).rstrip("/")
        self._project_id = project_id or settings.gitlab_project_id
        self._token = token or settings.gitlab_qa_token.get_secret_value()
        self._marker = comment_marker or settings.gitlab_comment_marker

    @property
    def configured(self) -> bool:
        return bool(self._api_url and self._project_id and self._token)

    async def upsert_mr_note(
        self,
        mr_iid: int,
        body: str,
        *,
        project_id: str | None = None,
    ) -> bool:
        """Create or update a QA report note on an MR.

        Uses the comment marker to find and update existing notes,
        preventing duplicate comments on repeated runs.
        """
        if not self.configured:
            logger.warning(
                "gitlab_not_configured",
                has_url=bool(self._api_url),
                has_project=bool(self._project_id),
                has_token=bool(self._token),
            )
            return False

        pid = project_id or self._project_id
        marked_body = f"{self._marker}\n{body}"
        base = f"{self._api_url}/projects/{pid}/merge_requests/{mr_iid}"
        headers = {"PRIVATE-TOKEN": self._token}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Find existing QA note
                existing_id = await self._find_marker_note(
                    client, base, headers,
                )

                if existing_id:
                    resp = await client.put(
                        f"{base}/notes/{existing_id}",
                        headers=headers,
                        json={"body": marked_body},
                    )
                    resp.raise_for_status()
                    logger.info(
                        "gitlab_note_updated",
                        mr_iid=mr_iid,
                        note_id=existing_id,
                    )
                else:
                    resp = await client.post(
                        f"{base}/notes",
                        headers=headers,
                        json={"body": marked_body},
                    )
                    resp.raise_for_status()
                    logger.info("gitlab_note_created", mr_iid=mr_iid)

                return True

        except Exception as e:
            logger.error(
                "gitlab_note_failed",
                mr_iid=mr_iid,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def _find_marker_note(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict,
    ) -> int | None:
        """Find existing note with QA marker."""
        try:
            resp = await client.get(
                f"{base_url}/notes",
                headers=headers,
                params={"per_page": 50, "sort": "desc"},
            )
            resp.raise_for_status()
            for note in resp.json():
                if self._marker in note.get("body", ""):
                    return note["id"]
        except Exception as e:
            logger.warning("gitlab_find_note_failed", error=str(e))
        return None
