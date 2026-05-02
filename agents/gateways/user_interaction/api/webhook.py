"""飞书 Webhook 处理 - 消息接收和去重"""
import asyncio
import hashlib
import json
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.integrations.feishu.cards.builder import CardBuilder
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

from ..service.agent import get_agent
from .schemas import ChallengeResponse, WebhookResponse

try:
    from ..app.metrics import CHAT_LATENCY, MESSAGE_DEDUP, MESSAGES_RECEIVED, MESSAGES_REPLIED
    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("chat_agent.webhook")

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Background task strong references (prevent GC of fire-and-forget tasks)
_background_tasks: set[asyncio.Task] = set()

# Redis connection for cross-worker message dedup
_redis: aioredis.Redis | None = None
_DEDUP_TTL = 300  # 5 minutes


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def _is_duplicate(msg_id: str) -> bool:
    r = _get_redis()
    was_set = await r.set(f"chat:dedup:{msg_id}", "1", nx=True, ex=_DEDUP_TTL)
    if not was_set:
        if _metrics_available:
            MESSAGE_DEDUP.inc()
        return True
    return False


@router.post("/feishu")
async def feishu_webhook(request: Request):
    """飞书事件回调"""
    raw_body = await request.body()
    body = json.loads(raw_body)

    # Signature verification (before any processing)
    if settings.feishu_verify_signature:
        client = get_feishu_client()
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        if not client.verify_signature(timestamp, nonce, raw_body, signature):
            logger.warning("webhook_signature_invalid")
            return JSONResponse(status_code=403, content={"detail": "Invalid signature"})

    # Challenge 验证
    if "challenge" in body:
        return ChallengeResponse(challenge=body["challenge"])

    # 解析事件
    header = body.get("header", {})
    event = body.get("event", {})
    event_type = header.get("event_type", "")

    if event_type != "im.message.receive_v1":
        return WebhookResponse()

    message = event.get("message", {})
    msg_id = message.get("message_id", "")
    msg_type = message.get("message_type", "")
    chat_type = message.get("chat_type", "")

    if await _is_duplicate(msg_id):
        logger.debug("msg_duplicate", msg_id=msg_id)
        return WebhookResponse()

    if msg_type != "text":
        return WebhookResponse()

    try:
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return WebhookResponse()

    if not text:
        return WebhookResponse()

    # 去掉 @机器人 的前缀
    if text.startswith("@"):
        parts = text.split(" ", 1)
        text = parts[1] if len(parts) > 1 else ""
    text = text.strip()
    if not text:
        return WebhookResponse()

    sender = event.get("sender", {}).get("sender_id", {})
    user_id = sender.get("open_id", "unknown")

    # Get user name (cached in Redis)
    user_name = ""
    try:
        r = _get_redis()
        cache_key = f"chat:user_info:{hashlib.sha256(user_id.encode()).hexdigest()[:16]}"
        cached = await r.get(cache_key)
        if cached:
            user_name = cached
        else:
            client = get_feishu_client()
            user_info = await client.get_user_info(user_id)
            user_name = user_info.get("name", "")
            if user_name:
                await r.setex(cache_key, 3600, user_name)  # Cache 1h
    except Exception:
        pass

    logger.info(
        "msg_received",
        user_hash=hashlib.sha256(user_id.encode()).hexdigest()[:12],
        chat_type=chat_type,
    )

    if _metrics_available:
        MESSAGES_RECEIVED.labels(chat_type=chat_type).inc()

    chat_id = message.get("chat_id", "")

    task = asyncio.create_task(
        _process_message(
            user_id, text, message, chat_type, user_name, chat_id,
        ),
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_error)

    return WebhookResponse()


def _log_task_error(task: asyncio.Task):
    """Log exceptions from background message processing tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("background_task_failed", error=str(exc))


async def _process_message(
    user_id: str,
    text: str,
    message: dict,
    chat_type: str,
    user_name: str = "",
    chat_id: str = "",
):
    """处理消息并回复"""
    msg_id = message.get("message_id", "")
    client = get_feishu_client()

    # 立即发送 emoji 表情反馈（让用户知道消息已收到）
    try:
        await client.add_reaction(msg_id, "OnIt")
    except Exception:
        pass  # 非关键路径，失败不影响主流程

    agent = get_agent()
    _start = time.time()
    try:
        result = await agent.handle_request({
            "action": "chat_user_assistant",
            "message": text,
            "user_id": user_id,
            "user_name": user_name,
            "chat_id": chat_id,
            "chat_type": chat_type,
        })
        reply = result.get("reply", "")
        elapsed = time.time() - _start

        # Card was already sent directly (propose_ tool) — skip reply
        if not reply:
            logger.info("msg_card_sent", user_id=user_id, elapsed=f"{elapsed:.1f}s")
            if _metrics_available:
                MESSAGES_REPLIED.labels(status="success").inc()
                CHAT_LATENCY.observe(elapsed)
            return

        # 构建卡片回复
        card = _build_reply_card(reply, elapsed)
        card_content = json.dumps(card, ensure_ascii=False)

        if chat_type == "p2p":
            await client.send_message(
                receive_id=user_id, receive_id_type="open_id",
                msg_type="interactive", content=card_content,
            )
        else:
            if msg_id:
                await client.reply_message(
                    message_id=msg_id, msg_type="interactive",
                    content=card_content,
                )

        logger.info("msg_replied", user_id=user_id, elapsed=f"{elapsed:.1f}s")
        if _metrics_available:
            MESSAGES_REPLIED.labels(status="success").inc()
            CHAT_LATENCY.observe(elapsed)

    except Exception as e:
        logger.error("msg_process_error", user_id=user_id, error=str(e))
        # Send error reply to user
        try:
            error_content = json.dumps(
                {"text": "抱歉，处理消息时出现问题，请稍后再试。"},
                ensure_ascii=False,
            )
            if chat_type == "p2p":
                await client.send_message(
                    receive_id=user_id, receive_id_type="open_id",
                    msg_type="text", content=error_content,
                )
            elif msg_id:
                await client.reply_message(
                    message_id=msg_id, msg_type="text",
                    content=error_content,
                )
        except Exception as reply_err:
            logger.error("error_reply_failed", user_id=user_id, error=str(reply_err))
        if _metrics_available:
            MESSAGES_REPLIED.labels(status="error").inc()


def _build_reply_card(reply: str, elapsed: float) -> dict:
    """构建 AI 回复卡片"""
    card = (
        CardBuilder()
        .set_header("🤖 项目经理", template="blue")
        .add_markdown(reply)
        .add_divider()
        .add_note(f"⏱ {elapsed:.1f}s · AI 生成，仅供参考 · Wisdoverse Cell")
        .build()
    )
    return card
