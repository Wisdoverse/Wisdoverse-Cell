"""Scratchpad — file-based global state for Coordinator Agent.

Directory structure:
    scratchpad/
      global_status.md          # Global project status summary
      workflows/{id}.md         # Per-workflow progress
      agents/{id}_output.md     # Per-agent latest output
      decisions/pending.md      # Pending decision queue
      decisions/log.md          # Decision history
"""
import os
from pathlib import Path

from shared.utils.logger import get_logger

logger = get_logger("infra.scratchpad")

_TOKEN_ESTIMATE_BYTES_PER_TOKEN = 4


class Scratchpad:
    """File-based scratchpad for Coordinator global state."""

    _COMPACT_TOKEN_THRESHOLD = 10000

    def __init__(self, base_dir: str = "data/scratchpad"):
        self._base = Path(base_dir)
        self._llm = None

    async def initialize(self) -> None:
        """Create directory structure and seed files."""
        for subdir in ["workflows", "agents", "decisions"]:
            (self._base / subdir).mkdir(parents=True, exist_ok=True)
        for seed in [
            "global_status.md",
            "decisions/pending.md",
            "decisions/log.md",
        ]:
            path = self._base / seed
            if not path.exists():
                path.write_text("")

    async def write_agent_output(self, agent_id: str, content: str) -> None:
        await self._write(f"agents/{agent_id}_output.md", content)

    async def write_workflow(self, workflow_id: str, content: str) -> None:
        await self._write(f"workflows/{workflow_id}.md", content)

    async def update_global_status(self, content: str) -> None:
        await self._write("global_status.md", content)

    async def append_decision(self, entry: str) -> None:
        path = self._base / "decisions" / "log.md"
        with open(path, "a") as f:
            f.write(f"\n{entry}")

    async def read_agent_output(self, agent_id: str) -> str:
        return await self._read(f"agents/{agent_id}_output.md")

    async def read_workflow(self, workflow_id: str) -> str:
        return await self._read(f"workflows/{workflow_id}.md")

    async def read_global_status(self) -> str:
        return await self._read("global_status.md")

    async def read_decision_log(self) -> str:
        return await self._read("decisions/log.md")

    async def read_incremental(self) -> str:
        """Read all scratchpad sections as a combined snapshot."""
        parts: list[str] = []
        status = await self.read_global_status()
        if status.strip():
            parts.append(f"## Global Status\n{status}")

        agents_dir = self._base / "agents"
        if agents_dir.is_dir():
            for f in sorted(agents_dir.glob("*_output.md")):
                content = f.read_text()
                if content.strip():
                    agent_id = f.stem.replace("_output", "")
                    parts.append(f"## Agent: {agent_id}\n{content}")

        workflows_dir = self._base / "workflows"
        if workflows_dir.is_dir():
            for f in sorted(workflows_dir.glob("*.md")):
                content = f.read_text()
                if content.strip():
                    wf_id = f.stem
                    parts.append(f"## Workflow: {wf_id}\n{content}")

        return "\n\n---\n\n".join(parts)

    async def estimate_tokens(self) -> int:
        """Rough token estimate: total bytes / 4."""
        total_bytes = 0
        for root, _dirs, files in os.walk(self._base):
            for fname in files:
                total_bytes += os.path.getsize(os.path.join(root, fname))
        return total_bytes // _TOKEN_ESTIMATE_BYTES_PER_TOKEN

    def should_compact(self) -> bool:
        """Check if compaction is needed based on total size."""
        total_bytes = 0
        for root, _dirs, files in os.walk(self._base):
            for fname in files:
                total_bytes += os.path.getsize(os.path.join(root, fname))
        estimate = total_bytes // _TOKEN_ESTIMATE_BYTES_PER_TOKEN
        return estimate > self._COMPACT_TOKEN_THRESHOLD

    async def compact(self) -> None:
        """L3 Full compaction using forked agent."""
        from shared.infra.forked_agent import run_forked

        if self._llm is None:
            logger.warning("scratchpad_compact_no_llm")
            return

        current = await self.read_incremental()
        if not current.strip():
            return

        result = await run_forked(
            llm=self._llm,
            prompt=f"Summarize this project state into a concise status update:\n\n{current}",
            system_prompt="You are a project state summarizer. Produce a concise markdown summary preserving all key information: active tasks, agent states, decisions, and blockers.",
            can_read=["data/scratchpad/**"],
            can_write=["data/scratchpad/global_status.md"],
            task_type="scratchpad_compact",
        )
        if result.success:
            await self.update_global_status(result.output)

    async def update(self, decisions: list) -> None:
        """Update scratchpad after decisions. Placeholder."""
        pass

    async def _write(self, rel_path: str, content: str) -> None:
        path = self._base / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    async def _read(self, rel_path: str) -> str:
        path = self._base / rel_path
        if not path.exists():
            return ""
        return path.read_text()
