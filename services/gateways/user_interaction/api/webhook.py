"""Feishu webhook handling for message intake and deduplication."""
import asyncio
import hashlib
import json
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

from ..core.card_ports import require_tool_card_renderer
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


def _hash_user_id(user_id: str) -> str:
    """Return a short one-way identifier for PII-safe logs."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


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
    """Handle Feishu event callbacks."""
    raw_body = await request.body()

    # Signature verification (before any processing)
    if settings.feishu_verify_signature:
        client = get_feishu_client()
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        if not client.verify_signature(timestamp, nonce, raw_body, signature):
            logger.warning("webhook_signature_invalid")
            return JSONResponse(status_code=403, content={"detail": "Invalid signature"})

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})

    # Challenge verification
    if "challenge" in body:
        return ChallengeResponse(challenge=body["challenge"])

    # Parse event payload
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

    # Remove the bot mention prefix.
    if text.startswith("@"):
        parts = text.split(" ", 1)
        text = parts[1] if len(parts) > 1 else ""
    text = text.strip()
    if not text:
        return WebhookResponse()

    sender = event.get("sender", {}).get("sender_id", {})
    user_id = sender.get("open_id", "unknown")
    user_hash = _hash_user_id(user_id)

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
        user_hash=user_hash,
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
    """Process the message and send a reply."""
    msg_id = message.get("message_id", "")
    client = get_feishu_client()
    user_hash = _hash_user_id(user_id)

    # Send an immediate reaction so the user knows the message was received.
    try:
        await client.add_reaction(msg_id, "OnIt")
    except Exception:
        pass  # Non-critical path.

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
            logger.info("msg_card_sent", user_hash=user_hash, elapsed=f"{elapsed:.1f}s")
            if _metrics_available:
                MESSAGES_REPLIED.labels(status="success").inc()
                CHAT_LATENCY.observe(elapsed)
            return

        # Build card reply.
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

        logger.info("msg_replied", user_hash=user_hash, elapsed=f"{elapsed:.1f}s")
        if _metrics_available:
            MESSAGES_REPLIED.labels(status="success").inc()
            CHAT_LATENCY.observe(elapsed)

    except Exception as e:
        logger.error("msg_process_error", user_hash=user_hash, error=str(e))
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
            logger.error("error_reply_failed", user_hash=user_hash, error=str(reply_err))
        if _metrics_available:
            MESSAGES_REPLIED.labels(status="error").inc()


def _build_reply_card(reply: str, elapsed: float) -> dict:
    """Build an AI reply card."""
    return require_tool_card_renderer().build_ai_reply_card(reply=reply, elapsed=elapsed)
