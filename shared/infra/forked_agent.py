"""Forked Agent — isolated LLM execution with permission whitelist.

Runs LLM tasks in a constrained context:
- Write permission: only whitelisted file paths
- Read permission: glob patterns (informational, not enforced at FS level)
- No EventBus access (isolation)
- Shared prompt cache flag for token savings

Used for: Scratchpad compaction, Agent Memory extraction, decision evaluation.
"""
from fnmatch import fnmatch

from pydantic import BaseModel

from shared.utils.logger import get_logger

logger = get_logger("infra.forked_agent")


class ForkedResult(BaseModel):
    """Result from a forked LLM execution."""

    success: bool
    output: str = ""
    error: str | None = None
    can_write: list[str] = []
    can_read: list[str] = []


def check_write_permission(file_path: str, can_write: list[str]) -> bool:
    """Check if a file path is allowed by the write whitelist."""
    for pattern in can_write:
        if fnmatch(file_path, pattern):
            return True
        if file_path == pattern:
            return True
    return False


async def run_forked(
    *,
    llm,
    prompt: str,
    system_prompt: str,
    can_read: list[str],
    can_write: list[str],
    share_prompt_cache: bool = True,
    task_type: str = "forked",
) -> ForkedResult:
    """Execute an LLM task in isolated context."""
    try:
        output = await llm.complete(
            prompt=prompt,
            agent_id="coordinator",
            task_type=task_type,
            system_prompt=system_prompt,
            max_tokens=4096,
        )
        return ForkedResult(
            success=True,
            output=output,
            can_write=can_write,
            can_read=can_read,
        )
    except Exception as e:
        logger.error("forked_agent_error", error=str(e))
        return ForkedResult(
            success=False,
            error=str(e),
            can_write=can_write,
            can_read=can_read,
        )
