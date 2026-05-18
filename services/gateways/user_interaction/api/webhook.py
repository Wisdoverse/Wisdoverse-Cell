"""Feishu webhook handling for message intake and deduplication."""
import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

from ..core.card_ports import require_tool_card_renderer
from ..core.webhook_intake import FeishuWebhookIntakeUseCase, hash_user_id
from ..core.webhook_processing import (
    WebhookMessageProcessingUseCase,
    WebhookProcessCommand,
)
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
_webhook_intake = FeishuWebhookIntakeUseCase()
_webhook_processing = WebhookMessageProcessingUseCase()


def _hash_user_id(user_id: str) -> str:
    """Return a short one-way identifier for PII-safe logs."""
    return hash_user_id(user_id)


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def _is_duplicate(msg_id: str) -> bool:
    duplicate = await _webhook_intake.is_duplicate(msg_id, _get_redis())
    if duplicate:
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

    incoming = _webhook_intake.extract_message_event(body)
    if incoming is None:
        return WebhookResponse()

    if await _is_duplicate(incoming.msg_id):
        logger.debug("msg_duplicate", msg_id=incoming.msg_id)
        return WebhookResponse()

    text = _webhook_intake.extract_text(incoming)
    if text is None:
        return WebhookResponse()

    user_hash = _hash_user_id(incoming.user_id)
    user_name = await _webhook_intake.resolve_user_name(
        incoming.user_id,
        cache=_get_redis(),
        user_directory=get_feishu_client(),
    )

    logger.info(
        "msg_received",
        user_hash=user_hash,
        chat_type=incoming.chat_type,
    )

    if _metrics_available:
        MESSAGES_RECEIVED.labels(chat_type=incoming.chat_type).inc()

    task = asyncio.create_task(
        _process_message(
            incoming.user_id,
            text,
            incoming.raw_message,
            incoming.chat_type,
            user_name,
            incoming.chat_id,
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
    user_hash = _hash_user_id(user_id)
    result = await _webhook_processing.process_message(
        WebhookProcessCommand(
            user_id=user_id,
            text=text,
            message=message,
            chat_type=chat_type,
            user_name=user_name,
            chat_id=chat_id,
        ),
        agent=get_agent(),
        messenger=get_feishu_client(),
        build_reply_card=_build_reply_card,
    )
    if result.status == "card_sent":
        logger.info("msg_card_sent", user_hash=user_hash, elapsed=f"{result.elapsed:.1f}s")
        if _metrics_available:
            MESSAGES_REPLIED.labels(status="success").inc()
            CHAT_LATENCY.observe(result.elapsed)
        return
    if result.status == "replied":
        logger.info("msg_replied", user_hash=user_hash, elapsed=f"{result.elapsed:.1f}s")
        if _metrics_available:
            MESSAGES_REPLIED.labels(status="success").inc()
            CHAT_LATENCY.observe(result.elapsed)
        return

    logger.error("msg_process_error", user_hash=user_hash, error=result.error)
    if result.reply_error:
        logger.error("error_reply_failed", user_hash=user_hash, error=result.reply_error)
    if _metrics_available:
        MESSAGES_REPLIED.labels(status="error").inc()


def _build_reply_card(reply: str, elapsed: float) -> dict:
    """Build an AI reply card."""
    return require_tool_card_renderer().build_ai_reply_card(reply=reply, elapsed=elapsed)
