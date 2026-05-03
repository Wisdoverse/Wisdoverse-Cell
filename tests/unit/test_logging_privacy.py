"""Static checks for PII-safe runtime logging."""

import ast
import re
from pathlib import Path

RUNTIME_ROOTS = ("agents", "services", "shared")
RAW_CONTENT_SLICE_LOG = re.compile(
    r"logger\.(?:debug|info|warning|error)\([^\n]*(?:content|message\.content)\[:"
)
RAW_LOG_KWARGS = {
    "approved_by",
    "content_preview",
    "chat_id",
    "data_preview",
    "email",
    "keyword",
    "message",
    "message_id",
    "open_id",
    "platform_chat_id",
    "platform_message_id",
    "phone",
    "platform_user_id",
    "payload",
    "raw_event_data",
    "raw",
    "receive_id",
    "rejected_by",
    "response",
    "raw_preview",
    "sender_id",
    "user",
    "user_id",
    "user_name",
    "text_preview",
}


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
        if RAW_CONTENT_SLICE_LOG.search(text):
            offenders.append(str(path))
            continue

        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"debug", "info", "warning", "error"}:
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "logger":
                continue
            bad_kwargs = [
                kw.arg
                for kw in node.keywords
                if kw.arg is not None and kw.arg in RAW_LOG_KWARGS
            ]
            if bad_kwargs:
                offenders.append(f"{path}:{node.lineno}:{','.join(bad_kwargs)}")

    assert offenders == []
