"""Static checks for PII-safe runtime logging."""

import re
from pathlib import Path

RUNTIME_ROOTS = ("agents", "services", "shared")
RAW_IDENTIFIER_LOG = re.compile(
    r"logger\.(?:debug|info|warning|error)\([^\n]*"
    r"(?:user_id|sender_id|receive_id|open_id|email|phone|content_preview)\s*="
)
RAW_CONTENT_SLICE_LOG = re.compile(
    r"logger\.(?:debug|info|warning|error)\([^\n]*(?:content|message\.content)\[:"
)


def _runtime_python_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    files: list[Path] = []
    for runtime_root in RUNTIME_ROOTS:
        for path in (root / runtime_root).rglob("*.py"):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_runtime_logs_do_not_emit_raw_pii_identifiers() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        text = path.read_text(encoding="utf-8")
        if RAW_IDENTIFIER_LOG.search(text) or RAW_CONTENT_SLICE_LOG.search(text):
            offenders.append(str(path))

    assert offenders == []
