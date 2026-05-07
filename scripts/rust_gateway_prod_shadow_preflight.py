#!/usr/bin/env python3
"""Preflight checks before writing production Rust gateway shadow evidence."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import ParseResult, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def main() -> int:
    errors = validate_prod_shadow_urls(
        os.getenv("GATEWAY_HOST", ""),
        os.getenv("LEGACY_GATEWAY_URL", ""),
        os.getenv("RUST_GATEWAY_URL", ""),
    )
    if errors:
        for error in errors:
            print(f"[fail] {error}", file=sys.stderr)
        return 2
    print("[ok] production shadow URLs are explicit and globally routable")
    return 0


def validate_prod_shadow_urls(gateway_host: str, legacy_url: str, rust_url: str) -> list[str]:
    from scripts.rust_gateway_prod_gate import is_local_url, is_placeholder_url

    errors: list[str] = []
    gateway_host = gateway_host.strip().lower().rstrip(".")
    legacy_url = legacy_url.strip()
    rust_url = rust_url.strip()
    legacy_url_valid_for_host_match = False

    if not gateway_host:
        errors.append("GATEWAY_HOST is required")

    for label, value in (
        ("LEGACY_GATEWAY_URL", legacy_url),
        ("RUST_GATEWAY_URL", rust_url),
    ):
        if not value:
            errors.append(f"{label} is required")
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{label} must be an absolute HTTP(S) URL")
            continue
        if parsed.scheme != "https":
            errors.append(f"{label} must use https for production gateway evidence")
            continue
        if not is_base_url(parsed):
            errors.append(f"{label} must be a base URL without path, query, or fragment")
            continue
        if is_placeholder_url(value):
            errors.append(f"{label} must not point to placeholder or documentation-only hosts")
            continue
        if is_local_url(value):
            errors.append(f"{label} must not point to local, private, or non-global hosts")
            continue
        if label == "LEGACY_GATEWAY_URL":
            legacy_url_valid_for_host_match = True

    if legacy_url and rust_url and legacy_url == rust_url:
        errors.append("LEGACY_GATEWAY_URL and RUST_GATEWAY_URL must differ")
    legacy_host = urlparse(legacy_url).hostname
    if (
        legacy_url_valid_for_host_match
        and gateway_host
        and legacy_host
        and gateway_host != legacy_host.lower().rstrip(".")
    ):
        errors.append("GATEWAY_HOST must match the host portion of LEGACY_GATEWAY_URL")

    return errors


def is_base_url(parsed: ParseResult) -> bool:
    return parsed.path in {"", "/"} and not parsed.params and not parsed.query and not parsed.fragment


if __name__ == "__main__":
    raise SystemExit(main())
