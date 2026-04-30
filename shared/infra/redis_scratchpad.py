"""RedisScratchpad — distributed shared state for cross-agent collaboration.

Redis-backed scratchpad that any agent can read/write. Same logical
sections as the file-based Scratchpad but distributed via Redis hashes.

Key schema:
    scratchpad:{namespace}:agents      → Hash {agent_id: content}
    scratchpad:{namespace}:workflows   → Hash {workflow_id: content}
    scratchpad:{namespace}:status      → String (global status)
    scratchpad:{namespace}:decisions   → List (append-only decision log)
"""
from shared.utils.logger import get_logger

logger = get_logger("infra.redis-scratchpad")

_PREFIX = "scratchpad"
_TOKEN_ESTIMATE_BYTES_PER_TOKEN = 4
_COMPACT_TOKEN_THRESHOLD = 10_000


class RedisScratchpad:
    """Redis-backed scratchpad for cross-agent shared state."""

    def __init__(self, redis, namespace: str = "default"):
        self._redis = redis
        self._ns = namespace

    def _key(self, section: str) -> str:
        return f"{_PREFIX}:{self._ns}:{section}"

    @staticmethod
    def _s(val) -> str:
        """Handle both bytes (decode_responses=False) and str (decode_responses=True)."""
        return val.decode() if isinstance(val, bytes) else val if val else ""

    # ── Agent outputs ───────────────────────────────────────────────────────

    async def write_agent_output(self, agent_id: str, content: str) -> None:
        await self._redis.hset(self._key("agents"), agent_id, content)

    async def read_agent_output(self, agent_id: str) -> str:
        val = await self._redis.hget(self._key("agents"), agent_id)
        return self._s(val)

    async def list_agents(self) -> list[str]:
        keys = await self._redis.hkeys(self._key("agents"))
        return [self._s(k) for k in keys]

    # ── Workflows ───────────────────────────────────────────────────────────

    async def write_workflow(self, workflow_id: str, content: str) -> None:
        await self._redis.hset(self._key("workflows"), workflow_id, content)

    async def read_workflow(self, workflow_id: str) -> str:
        val = await self._redis.hget(self._key("workflows"), workflow_id)
        return self._s(val)

    async def list_workflows(self) -> list[str]:
        keys = await self._redis.hkeys(self._key("workflows"))
        return [self._s(k) for k in keys]

    # ── Global status ───────────────────────────────────────────────────────

    async def update_global_status(self, content: str) -> None:
        await self._redis.set(self._key("status"), content)

    async def read_global_status(self) -> str:
        val = await self._redis.get(self._key("status"))
        return self._s(val)

    # ── Decision log ────────────────────────────────────────────────────────

    async def append_decision(self, entry: str) -> None:
        await self._redis.rpush(self._key("decisions"), entry)

    async def read_decision_log(self) -> str:
        entries = await self._redis.lrange(self._key("decisions"), 0, -1)
        return "\n".join(self._s(e) for e in entries)

    # ── Snapshot ────────────────────────────────────────────────────────────

    async def read_incremental(self) -> str:
        """Combine all sections into a single snapshot string."""
        parts: list[str] = []

        status = await self.read_global_status()
        if status.strip():
            parts.append(f"## Global Status\n{status}")

        agents = await self.list_agents()
        for aid in sorted(agents):
            content = await self.read_agent_output(aid)
            if content.strip():
                parts.append(f"## Agent: {aid}\n{content}")

        workflows = await self.list_workflows()
        for wid in sorted(workflows):
            content = await self.read_workflow(wid)
            if content.strip():
                parts.append(f"## Workflow: {wid}\n{content}")

        decisions = await self.read_decision_log()
        if decisions.strip():
            parts.append(f"## Decisions\n{decisions}")

        return "\n\n---\n\n".join(parts)

    # ── Token estimation ────────────────────────────────────────────────────

    async def estimate_tokens(self) -> int:
        """Rough token estimate from total stored bytes."""
        total = 0
        # agents hash
        vals = await self._redis.hvals(self._key("agents"))
        total += sum(len(v) for v in vals)
        # workflows hash
        vals = await self._redis.hvals(self._key("workflows"))
        total += sum(len(v) for v in vals)
        # status
        val = await self._redis.get(self._key("status"))
        if val:
            total += len(val)
        # decisions
        entries = await self._redis.lrange(self._key("decisions"), 0, -1)
        total += sum(len(e) for e in entries)

        return total // _TOKEN_ESTIMATE_BYTES_PER_TOKEN

    @staticmethod
    def should_compact_needed(token_count: int) -> bool:
        return token_count > _COMPACT_TOKEN_THRESHOLD
