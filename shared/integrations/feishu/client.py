"""
FeishuClient - 飞书 API 客户端

职责：
1. 通过 lark-oapi SDK 管理 API 调用（token 自动管理）
2. 请求签名验证
3. API 调用封装
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
    飞书 API 客户端（基于 lark-oapi SDK）

    使用方式:
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

        # 从 base_url 提取 domain（去掉 /open-apis 后缀）
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
        获取 access_token（用于健康检查/凭证验证）

        SDK 内部自动管理 token 缓存与刷新，此方法通过显式调用
        auth API 来验证凭证是否有效。
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
        验证飞书请求签名

        签名算法: SHA256(timestamp + nonce + encrypt_key + body)

        当签名验证被调用时，encrypt_key 必须配置。未配置时返回 False，
        避免在生产配置漂移时静默放行回调。
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

    # === 消息 API ===

    @feishu_error_handler("send_card")
    async def send_card(
        self,
        receive_id: str,
        receive_id_type: str,
        card: dict,
    ) -> str:
        """
        发送消息卡片

        Args:
            receive_id: 接收者 ID
            receive_id_type: ID 类型 ("open_id" | "chat_id" | "user_id")
            card: 卡片内容

        Returns:
            message_id

        Raises:
            FeishuAPIError: 发送失败时抛出
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
            message_id=response.data.message_id,
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
        发送消息（文本、富文本、卡片等通用消息）

        Args:
            receive_id: 接收者 ID
            receive_id_type: ID 类型 ("open_id" | "chat_id" | "user_id")
            msg_type: 消息类型 ("text" | "interactive" | "post" 等)
            content: 消息内容（已编码的 JSON 字符串，调用方自行序列化）

        Returns:
            message_id

        Raises:
            FeishuAPIError: 发送失败时抛出
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
            message_id=response.data.message_id,
        )
        return response.data.message_id

    @feishu_error_handler("update_card")
    async def update_card(
        self,
        message_id: str,
        card: dict,
    ) -> bool:
        """
        更新已发送的卡片

        用于操作后更新卡片状态（如确认后显示已确认）。

        Raises:
            FeishuAPIError: 更新失败时抛出
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
        logger.info("feishu_card_updated", message_id=message_id)
        return True

    @feishu_error_handler("reply_message")
    async def reply_message(
        self,
        message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> str:
        """
        回复消息

        Args:
            message_id: 要回复的消息 ID
            content: 回复内容
            msg_type: 消息类型

        Returns:
            新消息的 message_id

        Raises:
            FeishuAPIError: 回复失败时抛出
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
        给消息添加 emoji 表情回应

        Args:
            message_id: 消息 ID
            emoji_type: 表情类型 (如 "OnIt", "THUMBSUP", "HEART" 等)

        Returns:
            是否成功
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
            logger.info("feishu_reaction_added", message_id=message_id, emoji=emoji_type)
            return True
        except Exception as e:
            logger.warning("feishu_add_reaction_error", error=str(e))
            return False

    async def get_user_info(self, open_id: str) -> dict:
        """
        获取用户信息

        用于将 open_id 转换为用户名。
        注意：此方法不抛出异常，失败时返回默认值。
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
        """统一检查 SDK 响应"""
        if not response.success():
            raise FeishuAPIError(
                code=response.code,
                message=f"{operation}: {response.msg}",
            )


# 全局客户端实例（延迟初始化）
_feishu_client: Optional[FeishuClient] = None


def get_feishu_client() -> FeishuClient:
    """获取飞书客户端单例"""
    global _feishu_client
    if _feishu_client is None:
        _feishu_client = FeishuClient()
    return _feishu_client


feishu_client = get_feishu_client
