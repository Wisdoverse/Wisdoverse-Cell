"""Tests for Matrix adapter."""
pytest = __import__("pytest")
nio = pytest.importorskip("nio", reason="matrix-nio not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from shared.messaging.outbound.adapters._stable.matrix import MatrixAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import OutboundMessage


class TestMatrixAdapterAttributes:
    def test_channel_id(self):
        adapter = MatrixAdapter(
            homeserver="https://matrix.example.org",
            user_id="@bot:example.org",
            access_token="test_token",
        )
        assert adapter.channel_id == "matrix"

    def test_channel_name(self):
        adapter = MatrixAdapter(
            homeserver="https://matrix.example.org",
            user_id="@bot:example.org",
            access_token="test_token",
        )
        assert adapter.channel_name == "Matrix"

    def test_status_is_stable(self):
        adapter = MatrixAdapter(
            homeserver="https://matrix.example.org",
            user_id="@bot:example.org",
            access_token="test_token",
        )
        assert adapter.status == ChannelStatus.STABLE

    def test_capabilities(self):
        adapter = MatrixAdapter(
            homeserver="https://matrix.example.org",
            user_id="@bot:example.org",
            access_token="test_token",
        )
        # Matrix supports full capabilities
        assert ChannelCapability.TEXT in adapter.capabilities
        assert ChannelCapability.RICH_MEDIA in adapter.capabilities
        assert ChannelCapability.EDIT_MESSAGE in adapter.capabilities
        assert ChannelCapability.DELETE_MESSAGE in adapter.capabilities
        assert ChannelCapability.REACTIONS in adapter.capabilities
        assert ChannelCapability.READ_RECEIPTS in adapter.capabilities
        assert ChannelCapability.TYPING_INDICATOR in adapter.capabilities
        assert ChannelCapability.GROUP_MANAGEMENT in adapter.capabilities
        assert ChannelCapability.WEBHOOKS in adapter.capabilities


class TestMatrixAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_initializes_client(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            await adapter.connect()

            mock_client_class.assert_called_once_with(
                homeserver="https://matrix.example.org",
                user="@bot:example.org",
            )
            assert mock_client.access_token == "test_token"

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            await adapter.connect()
            await adapter.disconnect()

            mock_client.close.assert_called_once()


class TestMatrixAdapterSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.event_id = "$event123"
            mock_client.room_send.return_value = mock_response
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            await adapter.connect()

            message = OutboundMessage(
                channel_id="matrix",
                target_chat_id="!room123:example.org",
                content="Hello Matrix",
            )

            result = await adapter.send_message(message)

            assert result.success is True
            assert result.platform_message_id == "$event123"
            mock_client.room_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        adapter = MatrixAdapter(
            homeserver="https://matrix.example.org",
            user_id="@bot:example.org",
            access_token="test_token",
        )
        message = OutboundMessage(
            channel_id="matrix",
            target_chat_id="!room123:example.org",
            content="Hello",
        )
        result = await adapter.send_message(message)
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"


class TestMatrixAdapterEditDelete:
    @pytest.mark.asyncio
    async def test_delete_message_uses_redact(self):
        """Matrix uses room_redact for deleting messages."""
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.room_redact.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            adapter._room_id_cache["$event123"] = "!room123:example.org"
            await adapter.connect()

            result = await adapter.delete_message("$event123")

            assert result is True
            mock_client.room_redact.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_sends_replacement(self):
        """Matrix edits by sending a new message with m.new_content."""
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.event_id = "$event456"
            mock_client.room_send.return_value = mock_response
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            adapter._room_id_cache["$event123"] = "!room123:example.org"
            await adapter.connect()

            result = await adapter.edit_message("$event123", "New content")

            assert result is True
            mock_client.room_send.assert_called_once()


class TestMatrixAdapterReactions:
    @pytest.mark.asyncio
    async def test_add_reaction(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.room_send.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            adapter._room_id_cache["$event123"] = "!room123:example.org"
            await adapter.connect()

            result = await adapter.add_reaction("$event123", "👍")

            assert result is True
            mock_client.room_send.assert_called_once()
            call_args = mock_client.room_send.call_args
            assert call_args.kwargs["room_id"] == "!room123:example.org"
            assert call_args.kwargs["message_type"] == "m.reaction"

    @pytest.mark.asyncio
    async def test_add_reaction_not_connected(self):
        adapter = MatrixAdapter(
            homeserver="https://matrix.example.org",
            user_id="@bot:example.org",
            access_token="test_token",
        )
        result = await adapter.add_reaction("$event123", "👍")
        assert result is False


class TestMatrixAdapterTypingAndRead:
    @pytest.mark.asyncio
    async def test_send_typing_indicator(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            await adapter.connect()

            await adapter.send_typing_indicator("!room123:example.org")

            mock_client.room_typing.assert_called_once_with(
                room_id="!room123:example.org",
                typing_state=True,
            )

    @pytest.mark.asyncio
    async def test_mark_as_read(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.matrix.nio.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = MatrixAdapter(
                homeserver="https://matrix.example.org",
                user_id="@bot:example.org",
                access_token="test_token",
            )
            adapter._room_id_cache["$event123"] = "!room123:example.org"
            await adapter.connect()

            await adapter.mark_as_read("$event123")

            mock_client.room_read_markers.assert_called_once()
