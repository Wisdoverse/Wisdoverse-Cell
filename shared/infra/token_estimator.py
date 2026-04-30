"""Token estimation for Anthropic message arrays.

Estimates token counts from message JSON using byte-count heuristic (bytes / 4).
Separates tool_result tokens from text tokens for compression decision-making.
"""

import json
from dataclasses import dataclass

_BYTES_PER_TOKEN = 4


@dataclass(frozen=True)
class TokenEstimate:
    """Token count breakdown for a message array."""

    total_tokens: int
    tool_result_tokens: int
    text_tokens: int


def estimate_tokens(messages: list[dict]) -> TokenEstimate:
    """Estimate token counts for an Anthropic message array.

    Uses JSON byte length / 4 as heuristic. Separates tool_result
    content from other content to support selective trimming decisions.
    """
    if not messages:
        return TokenEstimate(total_tokens=0, tool_result_tokens=0, text_tokens=0)

    tool_result_bytes = 0
    total_bytes = 0

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_bytes += len(content.encode("utf-8"))
        elif isinstance(content, list):
            for block in content:
                block_json = json.dumps(block, ensure_ascii=False).encode("utf-8")
                block_bytes = len(block_json)
                total_bytes += block_bytes
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_result_bytes += block_bytes
        # Add overhead for role and structure
        total_bytes += len(json.dumps({"role": msg.get("role", "")}, ensure_ascii=False).encode("utf-8"))

    total_tokens = total_bytes // _BYTES_PER_TOKEN
    tool_result_tokens = tool_result_bytes // _BYTES_PER_TOKEN
    text_tokens = total_tokens - tool_result_tokens

    return TokenEstimate(
        total_tokens=total_tokens,
        tool_result_tokens=tool_result_tokens,
        text_tokens=text_tokens,
    )
