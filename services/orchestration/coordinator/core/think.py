"""LLM-powered decision engine for Coordinator."""
import json

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .models import Decision
from .prompts import build_system_prompt

logger = get_logger("coordinator.think")


async def think(context: dict, *, llm) -> list[Decision]:
    """Call LLM with context, return list of Decisions."""
    system_prompt = build_system_prompt()
    user_prompt = json.dumps(context, ensure_ascii=False, default=str)

    try:
        raw = await llm.complete(
            prompt=user_prompt,
            agent_id="coordinator",
            task_type="coordinator_synthesis",
            system_prompt=system_prompt,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("coordinator_think_llm_error")
        return []

    try:
        parsed = json.loads(raw)
        decisions_data = parsed.get("decisions", [])
        return [Decision(**d) for d in decisions_data]
    except (json.JSONDecodeError, Exception):
        logger.warning(
            "coordinator_think_parse_error",
            raw_response_hash=hash_identifier(raw, length=16),
            raw_response_length=len(raw),
        )
        return []
