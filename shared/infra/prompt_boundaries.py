"""Helpers for isolating untrusted source data in LLM prompts."""
from __future__ import annotations

import json
import re
from typing import Any

_TAG_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def dump_untrusted_json(data: Any) -> str:
    """Serialize data so it cannot close XML-style prompt boundaries."""
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).replace("</", "<\\/")


def wrap_untrusted_json(tag: str, data: Any) -> str:
    """Wrap JSON source data in a stable XML-style prompt boundary."""
    if not _TAG_PATTERN.fullmatch(tag):
        raise ValueError("prompt boundary tag must use letters, digits, dashes, or underscores")
    return f"<{tag}>\n{dump_untrusted_json(data)}\n</{tag}>"
