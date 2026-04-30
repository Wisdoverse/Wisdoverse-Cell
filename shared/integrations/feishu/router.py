"""
Feishu Webhook 统一入口

所有飞书回调都走这一个端点，内部根据类型分发：
- URL 验证（首次配置）
- 事件订阅
- Bot 消息
- 卡片回调
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from shared.config import settings
from shared.utils.logger import get_logger

from .client import feishu_client

logger = get_logger("feishu.router")

router = APIRouter(prefix="/api/feishu", tags=["feishu"])

# Handlers will be initialized later
event_handler = None
bot_handler = None
card_handler = None
message_recorder = None


def _secret_value(value) -> str:
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return str(value or "")


@router.post("/webhook")
async def feishu_webhook(
    request: Request,
    x_lark_request_timestamp: Optional[str] = Header(None),
    x_lark_request_nonce: Optional[str] = Header(None),
    x_lark_signature: Optional[str] = Header(None),
):
    """
    飞书统一回调入口

    处理类型：
    1. url_verification - 首次验证
    2. event_callback - 事件订阅
    3. card_action - 卡片回调
    """
    body = await request.body()
    data = await request.json()

    # 1. URL 验证（配置 Webhook 时飞书发送）
    if data.get("type") == "url_verification":
        logger.info("feishu_url_verification")
        return {"challenge": data["challenge"]}

    # 2. 签名验证（生产环境须同时配置 feishu_encrypt_key）
    if settings.feishu_verify_signature:
        if not _secret_value(settings.feishu_encrypt_key):
            logger.error("feishu_signature_verification_misconfigured", reason="encrypt_key_not_configured")
            raise HTTPException(status_code=401, detail="Signature verification key is not configured")

        client = feishu_client()
        if not client.verify_signature(
            timestamp=x_lark_request_timestamp or "",
            nonce=x_lark_request_nonce or "",
            body=body,
            signature=x_lark_signature or "",
        ):
            logger.warning("feishu_signature_invalid")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. 事件回调
    if data.get("type") == "event_callback":
        event_type = data.get("header", {}).get("event_type", "")
        logger.info("feishu_event_received", event_type=event_type)

        # 消息事件 → MessageRecorder + BotHandler
        if event_type == "im.message.receive_v1":
            event_data = data["event"]

            # Always try to record (recorder checks whitelist internally)
            if message_recorder and settings.feishu_message_recording_enabled:
                try:
                    await message_recorder.record(event_data)
                except Exception as e:
                    logger.error("message_recording_error", error=str(e))

            # Bot handler for @mentions (existing logic)
            if bot_handler and settings.feishu_bot_enabled:
                await bot_handler.handle_message(event_data)

            return {"code": 0}

        # 其他事件 → EventHandler
        if event_handler and settings.feishu_event_enabled:
            return await event_handler.dispatch(event_type, data)

        return {"code": 0}

    # 4. 卡片回调
    if data.get("type") == "card_action" or "action" in data:
        logger.info("feishu_card_action")
        if card_handler and settings.feishu_card_enabled:
            result = await card_handler.handle_action(data)
            if "card" in result:
                result["card"] = {"type": "raw", "data": result["card"]}
            return result
        return {"code": 0}

    logger.warning("feishu_unknown_callback", type=data.get("type"))
    return {"code": 0}


@router.get("/health")
async def feishu_health():
    """飞书集成健康检查"""
    if not settings.feishu_enabled:
        return {
            "status": "disabled",
            "feishu_enabled": False,
        }

    # Check token validity
    try:
        client = feishu_client()
        token = await client.get_access_token()
        token_valid = token is not None
    except Exception as e:
        logger.error("feishu_health_check_failed", error=str(e))
        token_valid = False

    return {
        "status": "healthy" if token_valid else "degraded",
        "feishu_enabled": True,
        "token_valid": token_valid,
        "bot_enabled": settings.feishu_bot_enabled,
        "event_enabled": settings.feishu_event_enabled,
        "card_enabled": settings.feishu_card_enabled,
    }


def init_handlers(event_h=None, bot_h=None, card_h=None, message_h=None):
    """Initialize handlers (called during app startup)"""
    global event_handler, bot_handler, card_handler, message_recorder
    event_handler = event_h
    bot_handler = bot_h
    card_handler = card_h
    message_recorder = message_h
