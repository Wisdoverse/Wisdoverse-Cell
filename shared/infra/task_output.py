"""DiskTaskOutput — disk-backed streaming output for long-running agent tasks.

Each task gets a single append-only output file. Consumers read via offset-based
delta reads, avoiding memory pressure from large outputs.
"""

import asyncio
import re
from pathlib import Path

_DEFAULT_MAX_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB
_VALID_TASK_ID = re.compile(r"[a-zA-Z0-9-]+")


class TaskOutputCapError(Exception):
    """Raised when an append would exceed the per-task output cap."""


class DiskTaskOutput:
    """Disk-backed output writer with offset-based delta reads."""

    def __init__(
        self,
        task_id: str,
        base_dir: str = "data/task_output",
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ):
        if not _VALID_TASK_ID.fullmatch(task_id):
            raise ValueError(
                f"Invalid task_id '{task_id}': must be alphanumeric + hyphens only"
            )
        self._task_id = task_id
        self._base = Path(base_dir)
        self._path = self._base / f"{task_id}.output"
        self._max_bytes = max_bytes
        self._lock = asyncio.Lock()

        # Validate resolved path stays inside base_dir
        resolved_base = self._base.resolve()
        resolved_path = self._path.resolve()
        if not str(resolved_path).startswith(str(resolved_base)):
            raise ValueError(f"Path traversal detected for task_id '{task_id}'")

    async def append(self, data: str) -> int:
        """Append data to the output file. Returns new file size.

        Raises TaskOutputCapError if the append would exceed max_bytes.
        """
        encoded = data.encode("utf-8")
        async with self._lock:
            await asyncio.to_thread(self._base.mkdir, parents=True, exist_ok=True)
            current_size = await asyncio.to_thread(
                lambda: self._path.stat().st_size if self._path.exists() else 0
            )
            if current_size + len(encoded) > self._max_bytes:
                raise TaskOutputCapError(
                    f"Append would exceed cap: {current_size} + {len(encoded)} > {self._max_bytes}"
                )
            await asyncio.to_thread(self._sync_write, encoded)
            return current_size + len(encoded)

    def _sync_write(self, data: bytes) -> None:
        with open(self._path, "ab") as f:
            f.write(data)

    async def read_delta(self, offset: int = 0) -> tuple[str, int]:
        """Read new data from offset. Returns (content, new_offset)."""
        result = await asyncio.to_thread(self._sync_read_delta, offset)
        return result

    def _sync_read_delta(self, offset: int) -> tuple[str, int]:
        if not self._path.exists():
            return ("", offset)
        file_size = self._path.stat().st_size
        if offset >= file_size:
            return ("", offset)
        with open(self._path, "rb") as f:
            f.seek(offset)
            data = f.read()
        return (data.decode("utf-8"), offset + len(data))

    async def read_all(self) -> str:
        """Read the entire output file."""
        content, _ = await self.read_delta(0)
        return content

    async def size(self) -> int:
        """Current file size in bytes."""
        return await asyncio.to_thread(
            lambda: self._path.stat().st_size if self._path.exists() else 0
        )

    async def close(self) -> None:
        """Clean up: delete file if empty or nonexistent."""
        def _cleanup():
            if self._path.exists() and self._path.stat().st_size == 0:
                self._path.unlink()
        await asyncio.to_thread(_cleanup)
