# Context Compressor

Token-aware, multi-layer compression for Anthropic message arrays.

## Quick Start

```python
from shared.infra.context_compressor import ContextCompressor, ContextCompressorConfig

compressor = ContextCompressor(
    ContextCompressorConfig(
        l1_threshold_tokens=40_000,   # Trigger L1 (tool-result trimming)
        l2_threshold_tokens=70_000,   # Trigger L2 (LLM summarization)
        keep_recent_messages=10,      # Keep N recent messages after L2
        keep_recent_tool_results=5,   # Keep N recent tool_results in L1
        summary_model="claude-haiku-4-5-20251001",
        agent_id="your-agent-id",
    ),
    llm=llm_gateway,  # Must have .complete() method
)

# In your conversation loop, before calling the LLM:
result = await compressor.compress_if_needed(messages)
messages = result.messages  # Use compressed messages

# result.layer: "none" | "L1" | "L2"
# result.tokens_before / result.tokens_after: for observability
```

## Layers

| Layer | Trigger | What It Does | Cost |
|-------|---------|-------------|------|
| L1 | `tokens >= l1_threshold` | Clears old tool_result content, keeps structure | Free |
| L2 | `tokens >= l2_threshold` (after L1) | Summarizes old messages via Haiku | ~500 tokens |

L1 runs first. If it reduces tokens below L2 threshold, L2 is skipped.

## Post-Compact Restoration

If your agent needs to re-inject context after compression (e.g., system state, active files):

```python
async def restore_context() -> list[dict]:
    return [{"role": "user", "content": "[System context] Current project state..."}]

compressor = ContextCompressor(
    config,
    llm=llm_gateway,
    post_compact_restore=restore_context,
)
```

The callback runs after L2 summarization. Its returned messages are appended to the compressed history.

## Reference: chat_agent Integration

See `services/gateways/user_interaction/core/chat_service.py` for the canonical integration example.
