"""
FeishuClient - Feishu API client.

Responsibilities:
1. Manage API calls through the lark-oapi SDK with automatic token handling.
2. Verify request signatures.
3. Wrap Feishu API calls.
"""
import asyncio
import hashlib
import hmac
import json
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.auth.v3 import (
    InternalTenantAccessTokenRequest,
    InternalTenantAccessTokenRequestBody,
)
from lark_oapi.api.contact.v3 import (
    BatchGetIdUserRequest,
    BatchGetIdUserRequestBody,
    GetUserRequest,
)
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    PatchMessageRequest,
    PatchMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from shared.config import settings
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .errors import FeishuAPIError, feishu_error_handler

logger = get_logger("feishu.client")


class FeishuClient:
    """
    Feishu API client based on the lark-oapi SDK.

    Usage:
        client = FeishuClient(app_id, app_secret)
        await client.send_card(chat_id, card)
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.app_id = app_id or settings.feishu_app_id
        _secret = settings.feishu_app_secret
        self.app_secret = app_secret or (_secret.get_secret_value() if _secret else "")
        self.base_url = base_url or settings.feishu_api_base_url

        # Extract the SDK domain from base_url by removing the /open-apis suffix.
        domain = self.base_url.removesuffix("/open-apis")

        self._sdk = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .domain(domain)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )

    async def get_access_token(self) -> str:
        """
        Get an access token for health checks and credential validation.

        The SDK manages token caching and refresh internally. This method calls
        the auth API explicitly to validate credentials.
        """
        request = (
            InternalTenantAccessTokenRequest.builder()
            .request_body(
                InternalTenantAccessTokenRequestBody.builder()
                .app_id(self.app_id)
                .app_secret(self.app_secret)
                .build()
            )
            .build()
        )
        response = await self._sdk.auth.v3.tenant_access_token.ainternal(request)
        if not response.success():
            raise FeishuAPIError(
                code=response.code,
                message=f"get_access_token: {response.msg}",
            )
        return response.tenant_access_token

    def verify_signature(
        self,
        timestamp: str,
        nonce: str,
        body: bytes,
        signature: str,
    ) -> bool:
        """
        Verify a Feishu request signature.

        Signature algorithm: SHA256(timestamp + nonce + encrypt_key + body).

        The encrypt_key must be configured when signature verification is used.
        Returning False for missing configuration avoids silently accepting
        callbacks when production configuration drifts.
        """
        encrypt_key = settings.feishu_encrypt_key.get_secret_value()
        if not encrypt_key:
            logger.error("feishu_signature_verification_misconfigured", reason="encrypt_key_not_configured")
            return False

        if not signature:
            logger.warning("feishu_signature_missing")
            return False

        content = f"{timestamp}{nonce}{encrypt_key}".encode() + body
        expected = hashlib.sha256(content).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning("feishu_signature_mismatch")
            return False

        return True

    # === Message API ===

    @feishu_error_handler("send_card")
    async def send_card(
        self,
        receive_id: str,
        receive_id_type: str,
        card: dict,
    ) -> str:
        """
        Send an interactive card message.

        Args:
            receive_id: Receiver ID.
            receive_id_type: ID type ("open_id" | "chat_id" | "user_id").
            card: Card content.

        Returns:
            message_id

        Raises:
            FeishuAPIError: Raised when sending fails.
        """
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("interactive")
                .content(json.dumps(card))
                .build()
            )
            .build()
        )
        response = await self._sdk.im.v1.message.acreate(request)
        self._check_response(response, "send_card")
        logger.info(
            "feishu_card_sent",
            receive_id_hash=hash_identifier(receive_id),
            message_hash=hash_identifier(response.data.message_id),
        )
        return response.data.message_id

    @feishu_error_handler("send_message")
    async def send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str = "text",
        content: str = "",
    ) -> str:
        """
        Send a generic message such as text, rich text, or card content.

        Args:
            receive_id: Receiver ID.
            receive_id_type: ID type ("open_id" | "chat_id" | "user_id").
            msg_type: Message type ("text" | "interactive" | "post", etc.).
            content: Message content as an encoded JSON string serialized by the caller.

        Returns:
            message_id

        Raises:
            FeishuAPIError: Raised when sending fails.
        """
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )
        response = await self._sdk.im.v1.message.acreate(request)
        self._check_response(response, "send_message")
        logger.info(
            "feishu_message_sent",
            receive_id_hash=hash_identifier(receive_id),
            msg_type=msg_type,
            message_hash=hash_identifier(response.data.message_id),
        )
        return response.data.message_id

    @feishu_error_handler("update_card")
    async def update_card(
        self,
        message_id: str,
        card: dict,
    ) -> bool:
        """
        Update a sent card.

        Used to update card state after an operation, for example after
        confirmation.

        Raises:
            FeishuAPIError: Raised when updating fails.
        """
        request = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(json.dumps(card))
                .build()
            )
            .build()
        )
        response = await self._sdk.im.v1.message.apatch(request)
        self._check_response(response, "update_card")
        logger.info("feishu_card_updated", message_hash=hash_identifier(message_id))
        return True

    @feishu_error_handler("reply_message")
    async def reply_message(
        self,
        message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> str:
        """
        Reply to a message.

        Args:
            message_id: Message ID to reply to.
            content: Reply content.
            msg_type: Message type.

        Returns:
            New message_id.

        Raises:
            FeishuAPIError: Raised when replying fails.
        """
        if msg_type == "text":
            encoded_content = json.dumps({"text": content})
        else:
            encoded_content = content

        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .msg_type(msg_type)
                .content(encoded_content)
                .build()
            )
            .build()
        )
        response = await self._sdk.im.v1.message.areply(request)
        self._check_response(response, "reply_message")
        return response.data.message_id

    async def add_reaction(self, message_id: str, emoji_type: str = "OnIt") -> bool:
        """
        Add an emoji reaction to a message.

        Args:
            message_id: Message ID.
            emoji_type: Emoji type such as "OnIt", "THUMBSUP", or "HEART".

        Returns:
            Whether the reaction succeeded.
        """
        from lark_oapi.api.im.v1 import (
            CreateMessageReactionRequest,
            CreateMessageReactionRequestBody,
            Emoji,
        )

        try:
            emoji = Emoji.builder().emoji_type(emoji_type).build()
            body = CreateMessageReactionRequestBody.builder().reaction_type(emoji).build()
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            response = await self._sdk.im.v1.message_reaction.acreate(request)
            if not response.success():
                logger.warning("feishu_add_reaction_failed", code=response.code, msg=response.msg)
                return False
            logger.info(
                "feishu_reaction_added",
                message_hash=hash_identifier(message_id),
                emoji=emoji_type,
            )
            return True
        except Exception as e:
            logger.warning("feishu_add_reaction_error", error=str(e))
            return False

    async def get_user_info(self, open_id: str) -> dict:
        """
        Get user information.

        Converts open_id to a display name. This method does not raise on
        failure; it returns a default value instead.
        """
        try:
            request = (
                GetUserRequest.builder()
                .user_id(open_id)
                .user_id_type("open_id")
                .build()
            )
            response = await self._sdk.contact.v3.user.aget(request)
            if not response.success():
                logger.warning(
                    "feishu_get_user_error",
                    code=response.code,
                    open_id_hash=hash_identifier(open_id),
                )
                return {"name": "Unknown", "open_id": open_id}
            user = response.data.user
            return {
                "name": user.name,
                "email": getattr(user, "email", ""),
                "open_id": open_id,
            }
        except Exception as e:
            logger.warning("feishu_get_user_error", error=str(e), open_id_hash=hash_identifier(open_id))
            return {"name": "Unknown", "open_id": open_id}

    async def lookup_user_ids(
        self,
        *,
        emails: list[str] | None = None,
        mobiles: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Resolve emails or mobile numbers into Feishu open IDs."""
        request = (
            BatchGetIdUserRequest.builder()
            .user_id_type("open_id")
            .request_body(
                BatchGetIdUserRequestBody.builder()
                .emails(emails or [])
                .mobiles(mobiles or [])
                .include_resigned(False)
                .build()
            )
            .build()
        )
        response = await asyncio.to_thread(self._sdk.contact.v3.user.batch_get_id, request)
        if not response.success() or not response.data:
            return []
        return [
            {"user_id": user.user_id}
            for user in (response.data.user_list or [])
            if user.user_id
        ]

    def _check_response(self, response, operation: str) -> None:
        """Check an SDK response consistently."""
        if not response.success():
            raise FeishuAPIError(
                code=response.code,
                message=f"{operation}: {response.msg}",
            )


# Global client instance, initialized lazily.
_feishu_client: Optional[FeishuClient] = None


def get_feishu_client() -> FeishuClient:
    """Return the FeishuClient singleton."""
    global _feishu_client
    if _feishu_client is None:
        _feishu_client = FeishuClient()
    return _feishu_client


feishu_client = get_feishu_client
