"""Unit tests for GitLab MR note client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.integrations.gitlab.client import GitLabClient


@pytest.fixture
def client():
    return GitLabClient(
        api_url="https://gitlab.example.com/api/v4",
        project_id="42",
        token="test-token",
        comment_marker="<!-- qa-test -->",
    )


@pytest.fixture
def unconfigured_client():
    return GitLabClient(api_url="", project_id="", token="")


class TestConfigured:
    def test_configured_when_all_set(self, client):
        assert client.configured is True

    def test_not_configured_when_missing(self, unconfigured_client):
        assert unconfigured_client.configured is False


class TestUpsertMrNote:
    @pytest.mark.asyncio
    async def test_creates_note_when_no_existing(self, client):
        mock_notes_resp = MagicMock()
        mock_notes_resp.json.return_value = []
        mock_notes_resp.raise_for_status = MagicMock()

        mock_create_resp = MagicMock()
        mock_create_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_notes_resp)
        mock_http.post = AsyncMock(return_value=mock_create_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_http):
            ok = await client.upsert_mr_note(10, "## Report")

        assert ok is True
        mock_http.post.assert_called_once()
        call_body = mock_http.post.call_args[1]["json"]["body"]
        assert "<!-- qa-test -->" in call_body
        assert "## Report" in call_body

    @pytest.mark.asyncio
    async def test_updates_note_when_existing(self, client):
        mock_notes_resp = MagicMock()
        mock_notes_resp.json.return_value = [
            {"id": 99, "body": "<!-- qa-test -->\nold report"},
        ]
        mock_notes_resp.raise_for_status = MagicMock()

        mock_update_resp = MagicMock()
        mock_update_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_notes_resp)
        mock_http.put = AsyncMock(return_value=mock_update_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_http):
            ok = await client.upsert_mr_note(10, "## New Report")

        assert ok is True
        mock_http.put.assert_called_once()
        assert "/notes/99" in str(mock_http.put.call_args)

    @pytest.mark.asyncio
    async def test_returns_false_when_unconfigured(self, unconfigured_client):
        ok = await unconfigured_client.upsert_mr_note(10, "report")
        assert ok is False

    @pytest.mark.asyncio
    async def test_returns_false_on_api_error(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_http.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_http):
            ok = await client.upsert_mr_note(10, "report")

        assert ok is False
