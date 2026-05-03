# shared/integrations/wecom/router.py
"""WeCom Webhook 统一入口"""

import base64
import hashlib
import hmac
import struct
from xml.etree.ElementTree import Element

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from defusedxml import ElementTree as ET
from fastapi import APIRouter, HTTPException, Query, Request

from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger("wecom.router")

router = APIRouter(prefix="/api/wecom", tags=["wecom"])

bot_handler = None
card_handler = None


def _is_production() -> bool:
    return str(getattr(settings, "app_env", "development")).lower() in {"production", "prod"}


def _callback_security_required() -> bool:
    return getattr(settings, "wecom_enabled", False) is True or _is_production()


def _secret_value(name: str) -> str:
    value = getattr(settings, name, "")
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        return str(getter() or "")
    return str(value or "")


def _wecom_crypto_config() -> tuple[str, str, str]:
    token = _secret_value("wecom_token")
    encoding_aes_key = _secret_value("wecom_encoding_aes_key")
    corp_id = str(getattr(settings, "wecom_corp_id", "") or "")

    missing = [
        name
        for name, value in (
            ("WECOM_TOKEN", token),
            ("WECOM_ENCODING_AES_KEY", encoding_aes_key),
            ("WECOM_CORP_ID", corp_id),
        )
        if not value
    ]
    if missing and _callback_security_required():
        raise HTTPException(
            status_code=503,
            detail=f"WeCom webhook security is not configured: {', '.join(missing)}",
        )
    return token, encoding_aes_key, corp_id


def _verify_wecom_signature(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    encrypted: str,
    token: str,
) -> bool:
    if not token:
        return not _callback_security_required()
    parts = [token, timestamp, nonce, encrypted]
    expected = hashlib.sha1("".join(sorted(parts)).encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, msg_signature)


def _decrypt_wecom_payload(encrypted: str, encoding_aes_key: str, corp_id: str) -> str:
    if len(encoding_aes_key) != 43:
        raise HTTPException(status_code=503, detail="Invalid WeCom EncodingAESKey length")

    try:
        aes_key = base64.b64decode(encoding_aes_key + "=")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Invalid WeCom EncodingAESKey") from exc

    try:
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16]))
        decryptor = cipher.decryptor()
        padded = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid WeCom ciphertext") from exc

    if not padded:
        raise HTTPException(status_code=403, detail="Invalid WeCom ciphertext")
    padding_len = padded[-1]
    if padding_len < 1 or padding_len > 32:
        raise HTTPException(status_code=403, detail="Invalid WeCom padding")

    plain = padded[:-padding_len]
    if len(plain) < 20:
        raise HTTPException(status_code=403, detail="Invalid WeCom payload")

    msg_len = struct.unpack(">I", plain[16:20])[0]
    msg_start = 20
    msg_end = msg_start + msg_len
    if len(plain) < msg_end:
        raise HTTPException(status_code=403, detail="Invalid WeCom message length")

    actual_corp_id = plain[msg_end:].decode("utf-8")
    if actual_corp_id != corp_id:
        raise HTTPException(status_code=403, detail="WeCom corp_id mismatch")

    return plain[msg_start:msg_end].decode("utf-8")


@router.get("/webhook")
async def wecom_verify(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """
    企微 URL 验证

    首次配置回调时，企微会发送 GET 请求验证 URL。
    """
    logger.info("wecom_url_verification", timestamp=timestamp)
    token, encoding_aes_key, corp_id = _wecom_crypto_config()
    if not token:
        return echostr
    if not _verify_wecom_signature(msg_signature, timestamp, nonce, echostr, token):
        raise HTTPException(status_code=403, detail="Invalid WeCom signature")
    return _decrypt_wecom_payload(echostr, encoding_aes_key, corp_id)


@router.post("/webhook")
async def wecom_webhook(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """企微消息回调"""
    body = await request.body()
    token, encoding_aes_key, corp_id = _wecom_crypto_config()

    try:
        root = ET.fromstring(body)
        encrypted = root.findtext("Encrypt")
        if encrypted:
            if not _verify_wecom_signature(msg_signature, timestamp, nonce, encrypted, token):
                raise HTTPException(status_code=403, detail="Invalid WeCom signature")
            root = ET.fromstring(_decrypt_wecom_payload(encrypted, encoding_aes_key, corp_id))
        elif _callback_security_required():
            raise HTTPException(status_code=400, detail="Missing encrypted WeCom payload")

        msg_type = root.find("MsgType")
        if msg_type is None:
            if _callback_security_required():
                raise HTTPException(status_code=400, detail="Missing WeCom message type")
            data = await request.json()
            return await _handle_card_callback(data)

        msg_type_text = msg_type.text
        logger.info("wecom_message_received", msg_type=msg_type_text)

        if msg_type_text == "text":
            if bot_handler and settings.wecom_bot_enabled:
                await bot_handler.handle_message(root)
            return "success"

        if msg_type_text == "event":
            event_type = root.find("Event")
            if event_type is not None and event_type.text == "template_card_event":
                return await _handle_card_event(root)

        return "success"

    except ET.ParseError as exc:
        if _callback_security_required():
            raise HTTPException(status_code=400, detail="Invalid WeCom XML payload") from exc
        data = await request.json()
        return await _handle_card_callback(data)


async def _handle_card_callback(data: dict) -> dict:
    if card_handler and settings.wecom_card_enabled:
        return await card_handler.handle_action(data)
    return {"errcode": 0}


async def _handle_card_event(root: Element) -> str:
    if card_handler and settings.wecom_card_enabled:
        data = {
            "FromUserName": root.find("FromUserName").text
            if root.find("FromUserName") is not None
            else "",
            "TaskId": root.find("TaskId").text if root.find("TaskId") is not None else "",
            "CardType": root.find("CardType").text if root.find("CardType") is not None else "",
            "ResponseCode": root.find("ResponseCode").text
            if root.find("ResponseCode") is not None
            else "",
            "SelectedItems": [],
        }

        selected = root.find("SelectedItems")
        if selected is not None:
            for item in selected.findall("SelectedItem"):
                question_key = item.find("QuestionKey")
                option_ids = item.find("OptionIds")
                if question_key is not None:
                    data["SelectedItems"].append(
                        {
                            "QuestionKey": question_key.text,
                            "OptionIds": option_ids.text if option_ids is not None else "",
                        }
                    )

        await card_handler.handle_event(data)

    return "success"


@router.get("/health")
async def wecom_health():
    """企微集成健康检查"""
    if not settings.wecom_enabled:
        return {
            "status": "disabled",
            "wecom_enabled": False,
        }

    return {
        "status": "healthy",
        "wecom_enabled": True,
        "bot_enabled": settings.wecom_bot_enabled,
        "card_enabled": settings.wecom_card_enabled,
    }


def init_handlers(bot_h=None, card_h=None):
    """Initialize handlers"""
    global bot_handler, card_handler
    bot_handler = bot_h
    card_handler = card_h
