# Agent Resilience Infrastructure v2 — Implementation Plan

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 resilience enhancements (output decline detection, dynamic compression, deferred tools, denial tracking, structured status) inspired by Claude Code v2.1.88 source patterns.

**Architecture:** Each enhancement is independently testable. E2 extends `AgentLoopCircuitBreaker` with output decline. E1 enhances `ContextCompressor` with dynamic thresholds and snip boundaries. E3 extends existing `ToolRegistry` with Anthropic schema generation and deferred loading. E4 adds `DenialTracker` wired into bitable reject flow. E5 adds `/status` endpoint reading Redis directly.

**Tech Stack:** Python 3.12+, asyncio, Redis (fakeredis for tests), Prometheus, Pydantic v2, pytest

**Spec:** Internal implementation spec is not part of the public distribution.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `shared/infra/agent_loop_breaker.py` | Modify | Add output_decline_count, output_lengths tracking |
| `shared/app/plugins/loop_breaker_plugin.py` | Modify | Pass output_length to record_round |
| `shared/infra/metrics.py` | Modify | Add LOOP_BREAKER_OUTPUT_DECLINE_RATIO gauge |
| `shared/tests/test_agent_loop_breaker.py` | Modify | Add output decline test class |
| `shared/infra/context_compressor.py` | Modify | Dynamic thresholds, snip indices, split-at-snip |
| `shared/tests/unit/test_context_compressor.py` | Modify | Add snip + dynamic threshold tests |
| `shared/infra/tool_registry.py` | Modify | Add to_anthropic_schemas, search_tools |
| `shared/tests/test_tool_registry.py` | Create | ToolRegistry extension tests |
| `shared/infra/denial_tracker.py` | Create | DenialTracker class |
| `shared/tests/test_denial_tracker.py` | Create | Denial record/check/clear/TTL tests |
| `agents/chat_agent/api/bitable.py` | Modify | Wire denial recording into reject endpoint |
| `agents/chat_agent/core/chat_service.py` | Modify | Denial check before propose_*, deferred tools |
| `agents/chat_agent/core/tools.py` | Modify | Add tool_search prompt text |
| `shared/infra/tool_validator.py` | Modify | Accept dynamic tool names |
| `shared/app/plugins/status_plugin.py` | Create | AgentStatusPlugin |
| `shared/app/plugins/__init__.py` | Modify | Export AgentStatusPlugin |
| `shared/app/factory.py` | Modify | Add /status endpoint |
| `shared/tests/test_status_plugin.py` | Create | Status endpoint tests |

---

## Task 1: E2 — Output Decline Detection (AgentLoopCircuitBreaker)

**Files:**
- Modify: `shared/infra/metrics.py`
- Modify: `shared/infra/agent_loop_breaker.py`
- Modify: `shared/tests/test_agent_loop_breaker.py`

### Step 1.1: Add Prometheus metric

- [ ] **Add output decline ratio gauge to metrics.py**

In `shared/infra/metrics.py`, append after the existing loop breaker metrics:

```python
LOOP_BREAKER_OUTPUT_DECLINE_RATIO = Gauge(
    "projectcell_loop_breaker_output_decline_ratio",
    "Latest output decline ratio (latest / mean_previous)",
    ["agent_id"],
)
```

### Step 1.2: Write failing tests for output decline

- [ ] **Add TestOutputDeclineDetection class to test_agent_loop_breaker.py**

Append to `shared/tests/test_agent_loop_breaker.py`:

```python
class TestOutputDeclineDetection:
    @pytest.mark.asyncio
    async def test_decline_skipped_when_no_output_length(self, breaker):
        """output_length=None → decline detection silently skipped."""
        await breaker.record_round(has_progress=True, output_length=None)
        state = await breaker.get_state()
        assert state["output_decline_count"] == 0

    @pytest.mark.asyncio
    async def test_no_decline_with_stable_output(self, redis):
        breaker = AgentLoopCircuitBreaker(
            agent_id="test-agent",
            no_progress_threshold=10,
            same_error_threshold=10,
            redis=redis,
        )
        for _ in range(5):
            await breaker.record_round(has_progress=True, output_length=1000)
        state = await breaker.get_state()
        assert state["output_decline_count"] == 0
        assert state["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_decline_detected_after_3_rounds(self, redis):
        breaker = AgentLoopCircuitBreaker(
            agent_id="test-agent",
            no_progress_threshold=10,
            same_error_threshold=10,
            output_decline_threshold=0.3,
            output_decline_rounds=3,
            redis=redis,
        )
        # Warm up with stable output
        for _ in range(3):
            await breaker.record_round(has_progress=True, output_length=1000)
        # Now send declining output (ratio < 0.3)
        for _ in range(3):
            await breaker.record_round(has_progress=True, output_length=50)
        state = await breaker.get_state()
        assert state["output_decline_count"] >= 3
        assert state["state"] == CircuitState.OPEN.value

    @pytest.mark.asyncio
    async def test_decline_resets_on_recovery(self, redis):
        breaker = AgentLoopCircuitBreaker(
            agent_id="test-agent",
            no_progress_threshold=10,
            same_error_threshold=10,
            output_decline_threshold=0.3,
            output_decline_rounds=5,
            redis=redis,
        )
        for _ in range(3):
            await breaker.record_round(has_progress=True, output_length=1000)
        # Two declining rounds
        await breaker.record_round(has_progress=True, output_length=50)
        await breaker.record_round(has_progress=True, output_length=50)
        # Recovery
        await breaker.record_round(has_progress=True, output_length=900)
        state = await breaker.get_state()
        assert state["output_decline_count"] == 0

    @pytest.mark.asyncio
    async def test_decline_needs_minimum_3_data_points(self, redis):
        breaker = AgentLoopCircuitBreaker(
            agent_id="test-agent",
            no_progress_threshold=10,
            same_error_threshold=10,
            redis=redis,
        )
        # Only 2 data points — not enough to compute decline
        await breaker.record_round(has_progress=True, output_length=1000)
        await breaker.record_round(has_progress=True, output_length=10)
        state = await breaker.get_state()
        assert state["output_decline_count"] == 0

    @pytest.mark.asyncio
    async def test_existing_tests_pass_without_output_length(self, breaker):
        """Backward compat: all existing record_round calls still work."""
        await breaker.record_round(has_progress=True)
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.HALF_OPEN.value
```

- [ ] **Run tests to verify they fail**

Run: `python -m pytest shared/tests/test_agent_loop_breaker.py::TestOutputDeclineDetection -v`
Expected: FAIL — `output_decline_count` not in state, `output_decline_threshold` not a parameter

### Step 1.3: Implement output decline in AgentLoopCircuitBreaker

- [ ] **Modify shared/infra/agent_loop_breaker.py**

Add import at top:

```python
from shared.infra.metrics import (
    LOOP_BREAKER_NO_PROGRESS_ROUNDS,
    LOOP_BREAKER_OUTPUT_DECLINE_RATIO,
    LOOP_BREAKER_STATE,
    LOOP_BREAKER_TRIPS_TOTAL,
)
```

Modify `__init__` to add new params:

```python
def __init__(
    self,
    agent_id: str,
    no_progress_threshold: int = 3,
    same_error_threshold: int = 5,
    half_open_threshold: int = 2,
    output_decline_threshold: float = 0.3,
    output_decline_rounds: int = 3,
    redis=None,
):
    self.agent_id = agent_id
    self.no_progress_threshold = no_progress_threshold
    self.same_error_threshold = same_error_threshold
    self.half_open_threshold = half_open_threshold
    self.output_decline_threshold = output_decline_threshold
    self.output_decline_rounds = output_decline_rounds
    self._redis = redis
    self._key = f"{_KEY_PREFIX}:{agent_id}"
    self._history_key = f"{_KEY_PREFIX}:{agent_id}:history"
    self._output_lengths_key = f"{_KEY_PREFIX}:{agent_id}:output_lengths"
```

Modify `_load` to include `output_decline_count`:

```python
async def _load(self) -> dict:
    raw = await self._redis.hgetall(self._key)
    if not raw:
        return {
            "state": CircuitState.CLOSED.value,
            "no_progress_count": 0,
            "same_error_count": 0,
            "last_error_signature": "",
            "total_opens": 0,
            "output_decline_count": 0,
        }
    def _get(key: str, default: str = "") -> str:
        return self._decode(raw.get(key, raw.get(key.encode(), default)))
    return {
        "state": _get("state", "closed"),
        "no_progress_count": int(_get("no_progress_count", "0")),
        "same_error_count": int(_get("same_error_count", "0")),
        "last_error_signature": _get("last_error_signature", ""),
        "total_opens": int(_get("total_opens", "0")),
        "output_decline_count": int(_get("output_decline_count", "0")),
    }
```

Modify `_save` to persist `output_decline_count`:

```python
async def _save(self, data: dict) -> None:
    await self._redis.hset(self._key, mapping={
        "state": data["state"],
        "no_progress_count": str(data["no_progress_count"]),
        "same_error_count": str(data["same_error_count"]),
        "last_error_signature": data["last_error_signature"],
        "total_opens": str(data["total_opens"]),
        "output_decline_count": str(data["output_decline_count"]),
    })
```

Add `_check_output_decline` method:

```python
async def _check_output_decline(self, output_length: int) -> float | None:
    """Track output length and return decline ratio, or None if insufficient data."""
    await self._redis.rpush(self._output_lengths_key, str(output_length))
    await self._redis.ltrim(self._output_lengths_key, -10, -1)

    raw_lengths = await self._redis.lrange(self._output_lengths_key, 0, -1)
    lengths = [int(self._decode(v)) for v in raw_lengths]

    if len(lengths) < 3:
        return None

    previous = lengths[:-1]
    latest = lengths[-1]
    mean_prev = sum(previous) / len(previous)
    if mean_prev == 0:
        return None

    ratio = latest / mean_prev
    LOOP_BREAKER_OUTPUT_DECLINE_RATIO.labels(agent_id=self.agent_id).set(ratio)
    return ratio
```

Modify `record_round` signature and add decline logic at the end of the method, BEFORE state transitions:

```python
async def record_round(
    self,
    has_progress: bool,
    error_signature: Optional[str] = None,
    output_length: Optional[int] = None,
) -> None:
    data = await self._load()
    old_state = data["state"]

    # Track error signature (unchanged)
    if error_signature:
        if error_signature == data["last_error_signature"]:
            data["same_error_count"] += 1
        else:
            data["same_error_count"] = 1
            data["last_error_signature"] = error_signature
    else:
        data["same_error_count"] = 0
        data["last_error_signature"] = ""

    # Track progress (unchanged)
    if has_progress:
        data["no_progress_count"] = 0
    else:
        data["no_progress_count"] += 1

    # NEW: Track output decline
    if output_length is not None and output_length > 0:
        ratio = await self._check_output_decline(output_length)
        if ratio is not None and ratio < self.output_decline_threshold:
            data["output_decline_count"] += 1
        elif ratio is not None:
            data["output_decline_count"] = 0
    # If output_length not provided, leave output_decline_count unchanged

    # State transitions
    new_state = old_state

    if data["same_error_count"] >= self.same_error_threshold:
        new_state = CircuitState.OPEN.value
    elif old_state == CircuitState.CLOSED.value:
        if (
            data["no_progress_count"] >= self.no_progress_threshold
            or data["output_decline_count"] >= self.output_decline_rounds
        ):
            new_state = CircuitState.OPEN.value
        elif (
            data["no_progress_count"] >= self.half_open_threshold
            or data["output_decline_count"] >= max(1, self.output_decline_rounds - 1)
        ):
            new_state = CircuitState.HALF_OPEN.value
    elif old_state == CircuitState.HALF_OPEN.value:
        if has_progress and data["same_error_count"] < self.same_error_threshold:
            if data["output_decline_count"] < self.output_decline_rounds:
                new_state = CircuitState.CLOSED.value
                data["no_progress_count"] = 0
                data["output_decline_count"] = 0
        elif (
            data["no_progress_count"] >= self.no_progress_threshold
            or data["output_decline_count"] >= self.output_decline_rounds
        ):
            new_state = CircuitState.OPEN.value

    if new_state == CircuitState.OPEN.value and old_state != CircuitState.OPEN.value:
        data["total_opens"] += 1

    data["state"] = new_state
    await self._save(data)
    self._emit_metrics(data, tripped=(new_state == CircuitState.OPEN.value and old_state != CircuitState.OPEN.value))

    if new_state != old_state:
        reason = (
            f"same_error({data['same_error_count']})"
            if data["same_error_count"] >= self.same_error_threshold
            else f"output_decline({data['output_decline_count']})"
            if data["output_decline_count"] >= self.output_decline_rounds
            else f"no_progress({data['no_progress_count']})"
            if not has_progress
            else "progress_recovered"
        )
        await self._record_transition(old_state, new_state, reason)
        logger.info(
            "loop_breaker_transition",
            agent_id=self.agent_id,
            from_state=old_state,
            to_state=new_state,
            reason=reason,
        )
```

Update `_emit_metrics` to include `output_decline` as a reason:

```python
def _emit_metrics(self, data: dict, *, tripped: bool = False) -> None:
    LOOP_BREAKER_STATE.labels(agent_id=self.agent_id).set(
        self._STATE_VALUES.get(data["state"], 0)
    )
    LOOP_BREAKER_NO_PROGRESS_ROUNDS.labels(agent_id=self.agent_id).set(
        data["no_progress_count"]
    )
    if tripped:
        if data["same_error_count"] >= self.same_error_threshold:
            reason = "same_error"
        elif data["output_decline_count"] >= self.output_decline_rounds:
            reason = "output_decline"
        else:
            reason = "no_progress"
        LOOP_BREAKER_TRIPS_TOTAL.labels(agent_id=self.agent_id, reason=reason).inc()
```

Update `reset` to clear output decline state:

```python
async def reset(self, reason: str = "manual") -> None:
    data = await self._load()
    old_state = data["state"]
    new_data = {
        "state": CircuitState.CLOSED.value,
        "no_progress_count": 0,
        "same_error_count": 0,
        "last_error_signature": "",
        "total_opens": data["total_opens"],
        "output_decline_count": 0,
    }
    await self._save(new_data)
    # Clear output lengths list
    await self._redis.delete(self._output_lengths_key)
    self._emit_metrics(new_data)
    if old_state != CircuitState.CLOSED.value:
        await self._record_transition(old_state, CircuitState.CLOSED.value, f"reset:{reason}")
        logger.info(
            "loop_breaker_reset",
            agent_id=self.agent_id,
            from_state=old_state,
            reason=reason,
        )
```

- [ ] **Run tests**

Run: `python -m pytest shared/tests/test_agent_loop_breaker.py -v`
Expected: ALL PASS (new + existing)

- [ ] **Commit**

```bash
git add shared/infra/agent_loop_breaker.py shared/infra/metrics.py shared/tests/test_agent_loop_breaker.py
git commit -m "feat(loop-breaker): add output decline detection

Tracks output_length per round in Redis, computes decline ratio
against rolling average. 3 consecutive rounds below 0.3 ratio
triggers HALF_OPEN → OPEN. Backward compatible (output_length=None
skips detection). Adds LOOP_BREAKER_OUTPUT_DECLINE_RATIO gauge."
```

### Step 1.4: Update LoopBreakerPlugin wrapper

- [ ] **Modify shared/app/plugins/loop_breaker_plugin.py**

In `_LoopBreakerAgentWrapper.handle_event`, pass `output_length`:

```python
async def handle_event(self, event: Event) -> list[Event]:
    if not await self._breaker.can_execute():
        raise AgentLoopBreakerError(self.agent_id)

    try:
        result = await self._inner.handle_event(event)
        output_length = sum(len(str(e.payload)) for e in result) if result else 0
        await self._breaker.record_round(has_progress=True, output_length=output_length)
        return result
    except AgentLoopBreakerError:
        raise
    except Exception as exc:
        sig = hashlib.md5(
            f"{type(exc).__name__}:{exc}".encode(), usedforsecurity=False
        ).hexdigest()[:16]
        await self._breaker.record_round(
            has_progress=False,
            error_signature=f"{type(exc).__name__}:{sig}",
            output_length=0,
        )
        raise
```

- [ ] **Run plugin tests**

Run: `python -m pytest shared/tests/test_loop_breaker_plugin.py -v`
Expected: ALL PASS

- [ ] **Commit**

```bash
git add shared/app/plugins/loop_breaker_plugin.py
git commit -m "feat(loop-breaker): pass output_length from plugin wrapper"
```

---

## Task 2: E1 — Dynamic Compression Thresholds + Snip Boundaries

**Files:**
- Modify: `shared/infra/context_compressor.py`
- Modify: `shared/tests/unit/test_context_compressor.py`

### Step 2.1: Write failing tests for dynamic thresholds

- [ ] **Add dynamic threshold tests to test_context_compressor.py**

Append to `shared/tests/unit/test_context_compressor.py`:

```python
class TestDynamicThresholds:
    """E1.R1-R3: max_context_tokens auto-calculates L1/L2 thresholds."""

    def test_auto_threshold_from_max_context(self):
        config = ContextCompressorConfig(
            max_context_tokens=200_000,
            l1_ratio=0.4,
            l2_ratio=0.6,
        )
        assert config.effective_l1_threshold == 80_000
        assert config.effective_l2_threshold == 120_000

    def test_explicit_threshold_overrides_auto(self):
        config = ContextCompressorConfig(
            max_context_tokens=200_000,
            l1_threshold_tokens=50_000,
            l2_threshold_tokens=90_000,
        )
        assert config.effective_l1_threshold == 50_000
        assert config.effective_l2_threshold == 90_000

    def test_no_max_context_uses_explicit_defaults(self):
        config = ContextCompressorConfig()
        assert config.effective_l1_threshold == 40_000
        assert config.effective_l2_threshold == 70_000

    def test_partial_override_l1_only(self):
        config = ContextCompressorConfig(
            max_context_tokens=200_000,
            l1_threshold_tokens=30_000,
        )
        # l1 explicit override, l2 auto-calculated
        assert config.effective_l1_threshold == 30_000
        assert config.effective_l2_threshold == 120_000  # 200K * 0.6
```

- [ ] **Run tests to verify they fail**

Run: `python -m pytest shared/tests/unit/test_context_compressor.py::TestDynamicThresholds -v`
Expected: FAIL — `effective_l1_threshold` not defined

### Step 2.2: Write failing tests for snip boundaries

- [ ] **Add snip boundary tests**

Append to `shared/tests/unit/test_context_compressor.py`:

```python
from shared.infra.context_compressor import find_snip_indices, find_split_point


class TestSnipBoundaries:
    """E1.R4-R9: Snip index tracking and split-at-snip."""

    def test_snip_indices_after_tool_sequences(self):
        messages = [{"role": "user", "content": "hi"}]
        messages.extend(_make_tool_round("tu_1", "search", "result1"))
        messages.extend(_make_tool_round("tu_2", "update", "result2"))
        messages.append({"role": "user", "content": "thanks"})

        indices = find_snip_indices(messages)
        # Snip after each tool_result message (indices 2 and 4)
        assert 2 in indices  # after first tool_result
        assert 4 in indices  # after second tool_result

    def test_no_snip_in_pure_text(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "bye"},
        ]
        indices = find_snip_indices(messages)
        assert indices == []

    def test_split_point_at_snip(self):
        # 10 messages, snip at 4 and 6, keep_recent=3 → target=7
        # nearest snip <= 7 is 6
        split = find_split_point(
            total_messages=10,
            snip_indices=[4, 6],
            keep_recent=3,
        )
        assert split == 6

    def test_split_point_fallback_when_no_snip(self):
        split = find_split_point(
            total_messages=10,
            snip_indices=[],
            keep_recent=3,
        )
        assert split == 7  # 10 - 3

    def test_split_point_snip_beyond_target_uses_fallback(self):
        # snip at 9 only, but target=7 → no snip <= 7
        split = find_split_point(
            total_messages=10,
            snip_indices=[9],
            keep_recent=3,
        )
        assert split == 7

    def test_no_orphaned_tool_use_after_split(self):
        """Split must not leave orphaned tool_use in recent portion."""
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "search", "r1"))
        messages.extend(_make_tool_round("tu_2", "update", "r2"))
        # tool_use at index 3 (assistant), tool_result at index 4 (user)
        # Split at index 3 would orphan tool_use → should not happen

        indices = find_snip_indices(messages)
        split = find_split_point(
            total_messages=len(messages),
            snip_indices=indices,
            keep_recent=2,
        )
        recent = messages[split:]
        # Validate no orphaned tool_use
        for msg in recent:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block["id"]
                        # Must have a matching tool_result in recent
                        has_result = any(
                            isinstance(m.get("content"), list)
                            and any(
                                isinstance(b, dict)
                                and b.get("type") == "tool_result"
                                and b.get("tool_use_id") == tool_id
                                for b in m["content"]
                            )
                            for m in recent
                        )
                        assert has_result, f"Orphaned tool_use {tool_id}"
```

- [ ] **Run tests to verify they fail**

Run: `python -m pytest shared/tests/unit/test_context_compressor.py::TestSnipBoundaries -v`
Expected: FAIL — `find_snip_indices` and `find_split_point` not defined

### Step 2.3: Implement dynamic thresholds and snip boundaries

- [ ] **Modify shared/infra/context_compressor.py**

Replace `ContextCompressorConfig` dataclass:

```python
@dataclass
class ContextCompressorConfig:
    """Per-agent compression configuration."""

    max_context_tokens: int | None = None
    l1_ratio: float = 0.40
    l2_ratio: float = 0.60
    l1_threshold_tokens: int = 40_000
    l2_threshold_tokens: int = 70_000
    keep_recent_messages: int = 10
    keep_recent_tool_results: int = 5
    summary_model: str = "claude-haiku-4-5-20251001"
    agent_id: str = "unknown"

    @property
    def effective_l1_threshold(self) -> int:
        if self.max_context_tokens is not None:
            auto = int(self.max_context_tokens * self.l1_ratio)
            # Explicit override: use it if it differs from the class default
            if self.l1_threshold_tokens != 40_000:
                return self.l1_threshold_tokens
            return auto
        return self.l1_threshold_tokens

    @property
    def effective_l2_threshold(self) -> int:
        if self.max_context_tokens is not None:
            auto = int(self.max_context_tokens * self.l2_ratio)
            if self.l2_threshold_tokens != 70_000:
                return self.l2_threshold_tokens
            return auto
        return self.l2_threshold_tokens
```

Add `find_snip_indices` and `find_split_point` functions:

```python
def find_snip_indices(messages: list[dict]) -> list[int]:
    """Find message indices where it is safe to split (after complete tool sequences).

    A snip index is placed after every tool_result message that completes a
    tool_use → tool_result pair. Splitting at a snip index guarantees no
    orphaned tool_use blocks in the recent portion.
    """
    indices: list[int] = []
    for i, msg in enumerate(messages):
        content = msg.get("content")
        if isinstance(content, list):
            has_tool_result = any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            )
            if has_tool_result:
                indices.append(i)
    return indices


def find_split_point(
    total_messages: int,
    snip_indices: list[int],
    keep_recent: int,
) -> int:
    """Find the best split point: nearest snip index at or before target.

    Target = total_messages - keep_recent.
    Falls back to target if no suitable snip index exists.
    """
    target = total_messages - keep_recent
    if target <= 0:
        return 0

    # Find largest snip index <= target
    best = None
    for idx in snip_indices:
        if idx <= target:
            best = idx

    return best if best is not None else target
```

Update `trim_tool_results` to return snip indices:

```python
def trim_tool_results(
    messages: list[dict],
    keep_recent: int = 5,
) -> tuple[CompactionResult, list[int]]:
    """L1: Clear old tool_result content, keep structure intact.

    Returns (CompactionResult, snip_indices) where snip_indices are safe
    split points after complete tool_use/tool_result sequences.
    """
    tokens_before = estimate_tokens(messages).total_tokens

    tool_result_positions: list[tuple[int, int]] = []
    for msg_idx, msg in enumerate(messages):
        content = msg.get("content")
        if isinstance(content, list):
            for block_idx, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_result_positions.append((msg_idx, block_idx))

    trim_count = max(0, len(tool_result_positions) - keep_recent)
    if trim_count == 0:
        snip_indices = find_snip_indices(messages)
        return CompactionResult(
            messages=deepcopy(messages),
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            layer="L1",
        ), snip_indices

    result_messages = deepcopy(messages)

    positions_to_trim = tool_result_positions[:trim_count]
    for msg_idx, block_idx in positions_to_trim:
        block = result_messages[msg_idx]["content"][block_idx]
        block["content"] = _TRIMMED_PLACEHOLDER

    tokens_after = estimate_tokens(result_messages).total_tokens
    snip_indices = find_snip_indices(result_messages)

    return CompactionResult(
        messages=result_messages,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        layer="L1",
    ), snip_indices
```

Update `summarize_history` to use snip-based splitting:

```python
async def summarize_history(
    messages: list[dict],
    config: ContextCompressorConfig,
    *,
    llm,
    snip_indices: list[int] | None = None,
) -> CompactionResult:
    """L2: Summarize old messages using LLM, keep recent ones.

    Splits at nearest snip boundary when available.
    """
    tokens_before = estimate_tokens(messages).total_tokens
    keep = config.keep_recent_messages

    if len(messages) <= keep:
        return CompactionResult(
            messages=messages,
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            layer="L2",
        )

    split_point = find_split_point(
        total_messages=len(messages),
        snip_indices=snip_indices or [],
        keep_recent=keep,
    )

    to_summarize = messages[:split_point]
    recent = messages[split_point:]

    if not to_summarize:
        return CompactionResult(
            messages=messages,
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            layer="L2",
        )

    summary_text = None
    try:
        prompt = _extract_text_for_summary(to_summarize)
        summary_text = await llm.complete(
            prompt=prompt,
            agent_id=config.agent_id,
            task_type="summarize",
            model=config.summary_model,
            max_tokens=500,
            system_prompt=_SUMMARY_SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.warning("summarize_failed", error=str(e))

    if not summary_text:
        tokens_after = estimate_tokens(recent).total_tokens
        return CompactionResult(
            messages=recent,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            layer="L2",
            summary=None,
        )

    boundary = {"role": "user", "content": f"[对话已压缩] {summary_text}"}
    ack = {"role": "assistant", "content": "好的，我已了解之前的对话内容。"}
    result_messages = [boundary, ack, *recent]

    tokens_after = estimate_tokens(result_messages).total_tokens
    return CompactionResult(
        messages=result_messages,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        layer="L2",
        summary=summary_text,
    )
```

Update `ContextCompressor.compress_if_needed` to use dynamic thresholds and pass snip_indices:

```python
async def compress_if_needed(
    self,
    messages: list[dict],
) -> CompactionResult:
    """Run L1 then L2 as needed based on token thresholds."""
    tokens = estimate_tokens(messages).total_tokens

    if tokens < self._config.effective_l1_threshold:
        return CompactionResult(
            messages=messages,
            tokens_before=tokens,
            tokens_after=tokens,
            layer="none",
        )

    l1_result, snip_indices = trim_tool_results(
        messages,
        keep_recent=self._config.keep_recent_tool_results,
    )

    logger.info(
        "context_compressed",
        layer="L1",
        tokens_before=l1_result.tokens_before,
        tokens_after=l1_result.tokens_after,
        agent_id=self._config.agent_id,
    )

    if l1_result.tokens_after < self._config.effective_l2_threshold:
        return l1_result

    l2_result = await summarize_history(
        l1_result.messages,
        self._config,
        llm=self._llm,
        snip_indices=snip_indices,
    )

    logger.info(
        "context_compressed",
        layer="L2",
        tokens_before=l2_result.tokens_before,
        tokens_after=l2_result.tokens_after,
        agent_id=self._config.agent_id,
    )

    if self._post_compact_restore and l2_result.summary:
        try:
            extra = await self._post_compact_restore()
            if extra:
                result_messages = [*l2_result.messages, *extra]
                tokens_after = estimate_tokens(result_messages).total_tokens
                return CompactionResult(
                    messages=result_messages,
                    tokens_before=l1_result.tokens_before,
                    tokens_after=tokens_after,
                    layer="L2",
                    summary=l2_result.summary,
                )
        except Exception as e:
            logger.warning("post_compact_restore_failed", error=str(e))

    return CompactionResult(
        messages=l2_result.messages,
        tokens_before=l1_result.tokens_before,
        tokens_after=l2_result.tokens_after,
        layer="L2",
        summary=l2_result.summary,
    )
```

- [ ] **Fix existing tests that call trim_tool_results (now returns tuple)**

In `shared/tests/unit/test_context_compressor.py`, update all existing calls to `trim_tool_results`:

Replace `result = trim_tool_results(...)` with `result, _snip = trim_tool_results(...)` in all existing test methods.

- [ ] **Run all compressor tests**

Run: `python -m pytest shared/tests/unit/test_context_compressor.py -v`
Expected: ALL PASS

- [ ] **Commit**

```bash
git add shared/infra/context_compressor.py shared/tests/unit/test_context_compressor.py
git commit -m "feat(compressor): dynamic thresholds + snip boundary splitting

ContextCompressorConfig.max_context_tokens enables auto-calculated
L1/L2 thresholds (40%/60% of window). Snip indices track safe split
points after tool_result sequences. L2 summarization splits at nearest
snip boundary to avoid orphaned tool_use blocks."
```

---

## Task 3: E3 — Deferred Tool Loading (ToolRegistry Extension)

**Files:**
- Create: `shared/tests/test_tool_registry.py`
- Modify: `shared/infra/tool_registry.py`
- Modify: `agents/chat_agent/core/tools.py`
- Modify: `agents/chat_agent/core/chat_service.py`
- Modify: `shared/infra/tool_validator.py`

### Step 3.1: Write failing tests for ToolRegistry extensions

- [ ] **Create shared/tests/test_tool_registry.py**

```python
"""ToolRegistry extension tests — Anthropic schema generation + deferred loading."""

import pytest

from shared.infra.tool_registry import ToolMeta, ToolRegistry, build_tool, ToolResult, ToolContext


async def _noop_handler(input: dict, context: ToolContext) -> ToolResult:
    return ToolResult(success=True)


def _make_registry() -> ToolRegistry:
    """Build a registry with 3 normal + 2 deferred tools."""
    reg = ToolRegistry()
    reg.register(build_tool("search", "Search records", _noop_handler))
    reg.register(build_tool("list_tasks", "List all tasks", _noop_handler))
    reg.register(build_tool("get_detail", "Get task detail", _noop_handler))
    reg.register(build_tool("sync_now", "Trigger sync", _noop_handler, should_defer=True))
    reg.register(build_tool("add_field", "Add a bitable field", _noop_handler, should_defer=True))
    return reg


class TestToAnthropicSchemas:
    def test_non_deferred_have_full_schema(self):
        reg = _make_registry()
        schemas = reg.to_anthropic_schemas()
        search = next(s for s in schemas if s["name"] == "search")
        assert "input_schema" in search
        assert search["input_schema"]["type"] == "object"

    def test_deferred_have_stub_schema(self):
        reg = _make_registry()
        schemas = reg.to_anthropic_schemas()
        sync = next(s for s in schemas if s["name"] == "sync_now")
        assert sync["input_schema"] == {"type": "object", "properties": {}}

    def test_active_deferred_get_full_schema(self):
        reg = _make_registry()
        schemas = reg.to_anthropic_schemas(active_deferred={"sync_now"})
        sync = next(s for s in schemas if s["name"] == "sync_now")
        assert sync["input_schema"]["type"] == "object"
        # add_field is still deferred (not in active set)
        add_f = next(s for s in schemas if s["name"] == "add_field")
        assert add_f["input_schema"] == {"type": "object", "properties": {}}

    def test_tool_search_always_included(self):
        reg = _make_registry()
        schemas = reg.to_anthropic_schemas()
        names = [s["name"] for s in schemas]
        assert "tool_search" in names

    def test_schema_count(self):
        reg = _make_registry()
        schemas = reg.to_anthropic_schemas()
        # 3 normal + 2 deferred stubs + 1 tool_search = 6
        assert len(schemas) == 6


class TestSearchTools:
    def test_search_by_name(self):
        reg = _make_registry()
        results = reg.search_tools("sync")
        assert len(results) == 1
        assert results[0]["name"] == "sync_now"

    def test_search_by_description(self):
        reg = _make_registry()
        results = reg.search_tools("field")
        assert len(results) == 1
        assert results[0]["name"] == "add_field"

    def test_search_returns_full_schema(self):
        reg = _make_registry()
        results = reg.search_tools("sync")
        assert "input_schema" in results[0]
        assert results[0]["input_schema"]["type"] == "object"

    def test_search_no_match(self):
        reg = _make_registry()
        results = reg.search_tools("nonexistent_xyz")
        assert results == []

    def test_search_includes_deferred_only(self):
        reg = _make_registry()
        # "search" is non-deferred — should NOT appear in search results
        results = reg.search_tools("search")
        deferred_names = {r["name"] for r in results}
        assert "search" not in deferred_names


class TestExistingMethodsUnchanged:
    def test_register_and_get(self):
        reg = _make_registry()
        assert reg.get("search") is not None
        assert reg.get("sync_now") is not None
        assert reg.get("nonexistent") is None

    def test_get_deferred(self):
        reg = _make_registry()
        deferred = reg.get_deferred()
        assert set(deferred) == {"sync_now", "add_field"}

    def test_get_read_only(self):
        reg = ToolRegistry()
        reg.register(build_tool("ro_tool", "Read only", _noop_handler, is_read_only=True))
        assert len(reg.get_read_only()) == 1
```

- [ ] **Run tests to verify they fail**

Run: `python -m pytest shared/tests/test_tool_registry.py -v`
Expected: FAIL — `to_anthropic_schemas` and `search_tools` not defined

### Step 3.2: Implement ToolRegistry extensions

- [ ] **Modify shared/infra/tool_registry.py**

Add these methods to the `ToolRegistry` class:

```python
def _tool_to_anthropic_schema(self, tool: Tool) -> dict:
    """Convert a Tool to Anthropic API tool schema format."""
    return {
        "name": tool.meta.name,
        "description": tool.meta.description,
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    }

@staticmethod
def tool_search_schema() -> dict:
    """Return the tool_search meta-tool definition."""
    return {
        "name": "tool_search",
        "description": "搜索可用的额外工具。输入关键词，返回匹配工具的完整定义。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（工具名称或描述）",
                },
            },
            "required": ["query"],
        },
    }

def to_anthropic_schemas(
    self, active_deferred: set[str] | None = None,
) -> list[dict]:
    """Generate Anthropic API tool schemas with deferred tool support.

    Non-deferred tools → full schema.
    Deferred tools in active_deferred → full schema (loaded by tool_search).
    Other deferred tools → stub (name + description only).
    Always includes tool_search meta-tool.
    """
    result: list[dict] = []
    for tool in self._tools.values():
        schema = self._tool_to_anthropic_schema(tool)
        if tool.meta.should_defer and not (active_deferred and tool.meta.name in active_deferred):
            # Stub: empty input_schema
            schema["input_schema"] = {"type": "object", "properties": {}}
        result.append(schema)
    result.append(self.tool_search_schema())
    return result

def search_tools(self, query: str) -> list[dict]:
    """Search deferred tools by name or description. Returns full schemas."""
    query_lower = query.lower()
    results: list[dict] = []
    for tool in self._tools.values():
        if not tool.meta.should_defer:
            continue
        if query_lower in tool.meta.name.lower() or query_lower in tool.meta.description.lower():
            results.append(self._tool_to_anthropic_schema(tool))
    return results
```

- [ ] **Run tests**

Run: `python -m pytest shared/tests/test_tool_registry.py -v`
Expected: ALL PASS

- [ ] **Commit**

```bash
git add shared/infra/tool_registry.py shared/tests/test_tool_registry.py
git commit -m "feat(tool-registry): add Anthropic schema generation + deferred search

to_anthropic_schemas() generates stub schemas for deferred tools,
full schemas for active tools, always includes tool_search meta-tool.
search_tools() enables LLM to discover deferred tools by keyword."
```

### Step 3.3: Wire deferred tools into chat_agent

- [ ] **Modify shared/infra/tool_validator.py — accept dynamic tool names**

```python
class ToolValidator:
    """Validates LLM tool_use blocks against registered tool definitions."""

    def __init__(
        self, *, registered_tools: list[dict], max_input_bytes: int = _MAX_TOOL_INPUT_BYTES
    ):
        self._tool_names = {t["name"] for t in registered_tools}
        self._max_input_bytes = max_input_bytes

    def add_tools(self, names: set[str]) -> None:
        """Dynamically add tool names (e.g., after tool_search loads deferred tools)."""
        self._tool_names |= names

    def validate_tool_use(self, tool_use: dict) -> None:
        name = tool_use.get("name", "")
        if name not in self._tool_names:
            logger.warning("unknown_tool_rejected", tool_name=name)
            raise ToolValidationError("unknown_tool", f"Tool '{name}' is not registered")

        tool_input = tool_use.get("input", {})
        size = len(json.dumps(tool_input, ensure_ascii=False).encode("utf-8"))
        if size > self._max_input_bytes:
            logger.warning("tool_input_too_large", tool_name=name, size=size)
            raise ToolValidationError(
                "tool_input_too_large",
                f"Tool input is {size} bytes, limit is {self._max_input_bytes}",
            )
```

- [ ] **Commit**

```bash
git add shared/infra/tool_validator.py
git commit -m "feat(tool-validator): add add_tools() for dynamic tool registration"
```

*Note: Chat agent wiring (modifying chat_service.py to use ToolRegistry + tool_search handling) is deferred to a follow-up PR. This task delivers the shared infrastructure; chat_agent integration requires careful testing with the full PM persona.*

---

## Task 4: E4 — Permission Denial Tracking

**Files:**
- Create: `shared/infra/denial_tracker.py`
- Create: `shared/tests/test_denial_tracker.py`
- Modify: `agents/chat_agent/api/bitable.py`

### Step 4.1: Write failing tests

- [ ] **Create shared/tests/test_denial_tracker.py**

```python
"""DenialTracker unit tests — record, check, clear, TTL."""

import pytest

fakeredis = pytest.importorskip("fakeredis")
fakeredis_aioredis = fakeredis.aioredis

from shared.infra.denial_tracker import DenialTracker


@pytest.fixture
async def redis():
    r = fakeredis_aioredis.FakeRedis()
    yield r
    await r.aclose()


@pytest.fixture
def tracker(redis):
    return DenialTracker(redis=redis, ttl=3600)


class TestRecordAndCheck:
    @pytest.mark.asyncio
    async def test_not_denied_initially(self, tracker):
        result = await tracker.is_denied("chat-agent", "user1", "create", "tbl_abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_denied_after_record(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="user1",
            action_type="create",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied("chat-agent", "user1", "create", "tbl_abc")
        assert result is not None
        assert result["reason"] == "user_rejected"

    @pytest.mark.asyncio
    async def test_different_user_not_denied(self, tracker):
        """Alice's denial must not block Bob."""
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="create",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied("chat-agent", "bob", "create", "tbl_abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_different_table_not_denied(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="user1",
            action_type="create",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied("chat-agent", "user1", "create", "tbl_xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_different_action_not_denied(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="user1",
            action_type="create",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied("chat-agent", "user1", "update", "tbl_abc")
        assert result is None


class TestClearDenials:
    @pytest.mark.asyncio
    async def test_clear_by_agent_and_user(self, tracker):
        await tracker.record_denial("chat-agent", "user1", "create", "tbl_a", "rejected")
        await tracker.record_denial("chat-agent", "user1", "update", "tbl_b", "rejected")
        cleared = await tracker.clear_denials("chat-agent", user_id="user1")
        assert cleared >= 2
        assert await tracker.is_denied("chat-agent", "user1", "create", "tbl_a") is None

    @pytest.mark.asyncio
    async def test_clear_does_not_affect_other_users(self, tracker):
        await tracker.record_denial("chat-agent", "alice", "create", "tbl_a", "rejected")
        await tracker.record_denial("chat-agent", "bob", "create", "tbl_a", "rejected")
        await tracker.clear_denials("chat-agent", user_id="alice")
        assert await tracker.is_denied("chat-agent", "bob", "create", "tbl_a") is not None


class TestMetrics:
    @pytest.mark.asyncio
    async def test_blocked_counter_increments(self, tracker):
        from shared.infra.denial_tracker import DENIAL_BLOCKED_TOTAL

        await tracker.record_denial("chat-agent", "u1", "create", "t1", "rejected")
        before = DENIAL_BLOCKED_TOTAL.labels(agent_id="chat-agent", action_type="create")._value.get()
        result = await tracker.is_denied("chat-agent", "u1", "create", "t1")
        assert result is not None
        after = DENIAL_BLOCKED_TOTAL.labels(agent_id="chat-agent", action_type="create")._value.get()
        assert after == before + 1
```

- [ ] **Run tests to verify they fail**

Run: `python -m pytest shared/tests/test_denial_tracker.py -v`
Expected: FAIL — module not found

### Step 4.2: Implement DenialTracker

- [ ] **Create shared/infra/denial_tracker.py**

```python
"""DenialTracker — remembers user-rejected actions to avoid re-proposing.

Redis key: denial:{agent_id}:{user_id}:{action_type}:{table_hash}
Value: JSON with reason + timestamps
TTL: configurable (default 3600s)
"""

import hashlib
import json
from datetime import UTC, datetime

from prometheus_client import Counter

from shared.utils.logger import get_logger

logger = get_logger("infra.denial-tracker")

DENIAL_BLOCKED_TOTAL = Counter(
    "projectcell_denial_tracker_blocked_total",
    "Total times a tool call was blocked by denial cache",
    ["agent_id", "action_type"],
)

_PREFIX = "denial"


class DenialTracker:
    """Redis-backed denial memory for Human-in-the-Loop flows."""

    def __init__(self, redis, ttl: int = 3600):
        self._redis = redis
        self._ttl = ttl

    @staticmethod
    def _key(agent_id: str, user_id: str, action_type: str, table_id: str) -> str:
        table_hash = hashlib.md5(table_id.encode(), usedforsecurity=False).hexdigest()[:12]
        return f"{_PREFIX}:{agent_id}:{user_id}:{action_type}:{table_hash}"

    async def record_denial(
        self,
        agent_id: str,
        user_id: str,
        action_type: str,
        table_id: str,
        reason: str,
    ) -> None:
        key = self._key(agent_id, user_id, action_type, table_id)
        value = json.dumps({
            "agent_id": agent_id,
            "user_id": user_id,
            "action_type": action_type,
            "table_id": table_id,
            "reason": reason,
            "denied_at": datetime.now(UTC).isoformat(),
        })
        await self._redis.set(key, value, ex=self._ttl)
        logger.info(
            "denial_recorded",
            agent_id=agent_id,
            user_id=user_id,
            action_type=action_type,
        )

    async def is_denied(
        self,
        agent_id: str,
        user_id: str,
        action_type: str,
        table_id: str,
    ) -> dict | None:
        key = self._key(agent_id, user_id, action_type, table_id)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        DENIAL_BLOCKED_TOTAL.labels(agent_id=agent_id, action_type=action_type).inc()
        return json.loads(raw)

    async def clear_denials(self, agent_id: str, user_id: str | None = None) -> int:
        pattern = f"{_PREFIX}:{agent_id}:{user_id or '*'}:*"
        cursor = 0
        cleared = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
                cleared += len(keys)
            if cursor == 0:
                break
        logger.info("denials_cleared", agent_id=agent_id, user_id=user_id, count=cleared)
        return cleared
```

- [ ] **Run tests**

Run: `python -m pytest shared/tests/test_denial_tracker.py -v`
Expected: ALL PASS

- [ ] **Commit**

```bash
git add shared/infra/denial_tracker.py shared/tests/test_denial_tracker.py
git commit -m "feat(denial-tracker): Redis-backed denial memory for HitL flows

Records user rejections keyed by agent_id + user_id + action_type +
table_id with configurable TTL. User-scoped (Alice denial != Bob denial).
Prometheus counter tracks blocked proposals."
```

### Step 4.3: Wire into bitable reject endpoint

- [ ] **Modify agents/chat_agent/api/bitable.py**

Add import and tracker init near top of file:

```python
from shared.infra.denial_tracker import DenialTracker
```

Add a module-level lazy getter (same pattern as existing `_get_redis()` in tools.py):

```python
_denial_tracker: DenialTracker | None = None


def get_denial_tracker() -> DenialTracker:
    global _denial_tracker
    if _denial_tracker is None:
        import redis.asyncio as aioredis
        from shared.config import settings
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        _denial_tracker = DenialTracker(redis=r)
    return _denial_tracker
```

In `reject_operation`, add denial recording after the existing `record_op` call:

```python
@router.post("/reject")
async def reject_operation(req: RejectRequest):
    """Record rejection and return a cancelled card dict."""
    action = f"reject_{req.action_type}" if req.action_type else "reject"
    task = asyncio.create_task(record_op(
        user_id=req.user_id, user_name=req.user_name,
        action=action, result="rejected",
        table_id=req.table_id, record_id=req.record_id, fields=req.fields,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Record denial for future blocking
    if req.action_type and req.user_id:
        try:
            tracker = get_denial_tracker()
            await tracker.record_denial(
                agent_id="chat-agent",
                user_id=req.user_id,
                action_type=req.action_type,
                table_id=req.table_id or "",
                reason="user_rejected",
            )
        except Exception as e:
            logger.warning("denial_tracking_failed", error=str(e))

    if req.action_type == "create":
        title = "🚫 已取消创建"
        text = "用户已取消此次任务创建。"
    else:
        title = "🚫 已取消修改"
        text = "用户已取消此次表格修改。"
    return CardBuilder().set_header(title, template="grey").add_markdown(text).build()
```

- [ ] **Commit**

```bash
git add agents/chat_agent/api/bitable.py
git commit -m "feat(chat-agent): record denials in bitable reject endpoint"
```

---

## Task 5: E5 — Structured Agent Status

**Files:**
- Create: `shared/app/plugins/status_plugin.py`
- Create: `shared/tests/test_status_plugin.py`
- Modify: `shared/app/plugins/__init__.py`
- Modify: `shared/app/factory.py`

### Step 5.1: Write failing tests

- [ ] **Create shared/tests/test_status_plugin.py**

```python
"""AgentStatusPlugin unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.app.plugins.status_plugin import AgentStatusPlugin, build_status


class TestAgentStatusPlugin:
    def test_plugin_name(self):
        plugin = AgentStatusPlugin()
        assert plugin.name == "agent-status"

    @pytest.mark.asyncio
    async def test_health_check_always_ok(self):
        plugin = AgentStatusPlugin()
        checks = await plugin.health_check()
        assert checks == {}

    def test_contribute_status_returns_uptime(self):
        plugin = AgentStatusPlugin()
        plugin._started_at = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
        status = plugin.contribute_status()
        assert "uptime_seconds" in status
        assert "started_at" in status
        assert status["uptime_seconds"] > 0


class TestBuildStatus:
    @pytest.mark.asyncio
    async def test_basic_status_shape(self):
        runtime = MagicMock()
        runtime.agent.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")
        assert status["agent_id"] == "test-agent"
        assert status["state"] == "running"
        assert "loop_breaker" in status

    @pytest.mark.asyncio
    async def test_loop_breaker_from_redis(self):
        runtime = MagicMock()
        runtime.agent.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={
            "state": "half_open",
            "no_progress_count": "2",
            "same_error_count": "0",
            "output_decline_count": "1",
            "total_opens": "3",
        })

        status = await build_status(runtime, redis, agent_id="test-agent")
        assert status["loop_breaker"]["state"] == "half_open"
        assert status["loop_breaker"]["no_progress_count"] == 2
        assert status["loop_breaker"]["output_decline_count"] == 1

    @pytest.mark.asyncio
    async def test_plugin_contributions(self):
        plugin = MagicMock()
        plugin.name = "test-plugin"
        plugin.contribute_status = MagicMock(return_value={"key": "value"})

        runtime = MagicMock()
        runtime.agent.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = [plugin]

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")
        assert status["plugins"]["test-plugin"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_missing_redis_data_graceful(self):
        runtime = MagicMock()
        runtime.agent.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")
        assert status["loop_breaker"] == {}
```

- [ ] **Run tests to verify they fail**

Run: `python -m pytest shared/tests/test_status_plugin.py -v`
Expected: FAIL — module not found

### Step 5.2: Implement AgentStatusPlugin

- [ ] **Create shared/app/plugins/status_plugin.py**

```python
"""AgentStatusPlugin — exposes structured runtime status via /status endpoint."""

from datetime import UTC, datetime

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.utils.logger import get_logger

logger = get_logger("plugin.agent-status")

_LOOP_BREAKER_KEY_PREFIX = "loop_breaker"


class AgentStatusPlugin(RuntimePlugin):
    """Collects and exposes structured agent runtime status."""

    name = "agent-status"

    def __init__(self):
        self._started_at: datetime | None = None

    async def startup(self, runtime) -> None:
        self._started_at = datetime.now(UTC)

    def contribute_status(self) -> dict:
        now = datetime.now(UTC)
        uptime = (now - self._started_at).total_seconds() if self._started_at else 0
        return {
            "uptime_seconds": int(uptime),
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }

    async def health_check(self) -> dict[str, HealthCheckResult]:
        return {}


async def build_status(runtime, redis, *, agent_id: str) -> dict:
    """Build the full status document. Called on-demand by /status endpoint."""
    status: dict = {
        "agent_id": agent_id,
        "state": "running" if runtime.is_started else "starting",
    }

    # Loop breaker state — read directly from Redis (bypasses wrapper)
    try:
        raw = await redis.hgetall(f"{_LOOP_BREAKER_KEY_PREFIX}:{agent_id}")
        if raw:
            def _s(v):
                return v.decode() if isinstance(v, bytes) else v if v else ""

            status["loop_breaker"] = {
                "state": _s(raw.get("state", raw.get(b"state", ""))),
                "no_progress_count": int(_s(raw.get("no_progress_count", raw.get(b"no_progress_count", "0")))),
                "same_error_count": int(_s(raw.get("same_error_count", raw.get(b"same_error_count", "0")))),
                "output_decline_count": int(_s(raw.get("output_decline_count", raw.get(b"output_decline_count", "0")))),
                "total_opens": int(_s(raw.get("total_opens", raw.get(b"total_opens", "0")))),
            }
        else:
            status["loop_breaker"] = {}
    except Exception as e:
        logger.warning("status_loop_breaker_failed", error=str(e))
        status["loop_breaker"] = {}

    # Plugin contributions
    status["plugins"] = {}
    for plugin in runtime._plugins:
        if hasattr(plugin, "contribute_status"):
            try:
                status["plugins"][plugin.name] = plugin.contribute_status()
            except Exception as e:
                logger.warning("plugin_status_failed", plugin=plugin.name, error=str(e))

    return status
```

- [ ] **Run tests**

Run: `python -m pytest shared/tests/test_status_plugin.py -v`
Expected: ALL PASS

- [ ] **Commit**

```bash
git add shared/app/plugins/status_plugin.py shared/tests/test_status_plugin.py
git commit -m "feat(status-plugin): structured agent status with Redis-direct reads

AgentStatusPlugin + build_status() reads loop breaker state from Redis
directly (works even when routes bypass runtime.agent). Collects
plugin contributions via contribute_status() protocol."
```

### Step 5.3: Wire /status endpoint and export

- [ ] **Modify shared/app/plugins/__init__.py**

Add export:

```python
from shared.app.plugins.status_plugin import AgentStatusPlugin
```

- [ ] **Modify shared/app/factory.py — add /status endpoint**

After the `/health/startup` endpoint block, add:

```python
@app.get("/status", tags=["health"], dependencies=[Depends(verify_internal_key)])
async def status_endpoint(request: Request):
    from shared.app.plugins.status_plugin import build_status
    redis = getattr(request.app.state, "redis", None)
    status = await build_status(runtime, redis, agent_id=runtime.agent_id)
    return JSONResponse(content=status)
```

- [ ] **Commit**

```bash
git add shared/app/plugins/__init__.py shared/app/factory.py
git commit -m "feat(factory): add /status endpoint with internal auth"
```

---

## Task 6: Run Full Test Suite + Lint

- [ ] **Run all tests**

```bash
python -m pytest shared/tests/ -v --tb=short
```

Expected: ALL PASS

- [ ] **Run linter**

```bash
ruff check shared/ agents/chat_agent/
```

Expected: No errors

- [ ] **Final commit if lint fixes needed**

```bash
git add -u
git commit -m "fix: lint cleanup for resilience v2"
```
