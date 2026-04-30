"""AgentMemory — three-scope persistent memory system.

Scopes:
- global: data/agent-memory/global/ — shared by all agents (coordinator-writable)
- agent: data/agent-memory/{agent_id}/ — per-agent knowledge
- workflow: data/agent-memory/workflows/{workflow_id}/ — per-workflow context

Each scope has MEMORY.md index + detail markdown files.
"""
from pathlib import Path

from shared.utils.logger import get_logger

logger = get_logger("infra.agent_memory")


class AgentMemory:
    """Three-scope persistent memory with permission isolation."""

    def __init__(
        self,
        agent_id: str,
        base_dir: str = "data/agent-memory",
        *,
        is_coordinator: bool = False,
    ):
        self._agent_id = agent_id
        self._base = Path(base_dir)
        self._is_coordinator = is_coordinator

    async def load_context(self, workflow_id: str | None = None) -> str:
        """Load memory as LLM context prefix. Reads all applicable scopes."""
        parts: list[str] = []
        global_ctx = await self._read_scope("global")
        if global_ctx:
            parts.append(global_ctx)
        agent_ctx = await self._read_scope(self._agent_id)
        if agent_ctx:
            parts.append(agent_ctx)
        if workflow_id:
            wf_ctx = await self._read_scope(f"workflows/{workflow_id}")
            if wf_ctx:
                parts.append(wf_ctx)
        return "\n---\n".join(parts)

    async def save(
        self,
        scope: str,
        key: str,
        content: str,
        *,
        workflow_id: str | None = None,
    ) -> None:
        """Write to memory with permission isolation.

        Args:
            scope: "global" | agent_id | "workflows/{workflow_id}"
            key: filename (e.g., "patterns.md")
            content: markdown content
            workflow_id: required when writing to workflow scope
        """
        self._check_permission(scope, workflow_id)
        path = self._base / scope / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        logger.debug("Saved memory: scope=%s key=%s agent=%s", scope, key, self._agent_id)

    async def _read_scope(self, scope: str) -> str:
        """Read all markdown files in a scope, concatenated."""
        scope_dir = self._base / scope
        if not scope_dir.is_dir():
            return ""
        parts: list[str] = []
        for f in sorted(scope_dir.glob("*.md")):
            content = f.read_text()
            if content.strip():
                parts.append(content)
        return "\n\n".join(parts)

    def _check_permission(self, scope: str, workflow_id: str | None) -> None:
        """Enforce write permission rules."""
        if self._is_coordinator:
            return  # Coordinator can write anywhere
        allowed = {self._agent_id}
        if workflow_id:
            allowed.add(f"workflows/{workflow_id}")
        if scope not in allowed:
            raise PermissionError(
                f"Agent {self._agent_id} cannot write to scope '{scope}'"
            )
