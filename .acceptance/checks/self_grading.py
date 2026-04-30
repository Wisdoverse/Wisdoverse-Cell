"""
L1 CHECK: Self-Grading Test Detection
=======================================
Detects when tests likely only cover happy paths — a common pattern
when AI generates both implementation and tests in the same session.

Signals:
  - High ratio of happy-path-only tests (no error assertions)
  - No pytest.raises or exception handling in test code
  - All test names are positive ("test_success", "test_create")
    with no negative tests ("test_invalid", "test_error", "test_fail")
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def check_self_grading(files: list[Path], config: dict) -> list[dict]:
    """Analyze test files for happy-path-only patterns."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from runner import CheckResult

    l1_conf = config.get("l1_check", {}).get("self_grading_detection", {})
    if not l1_conf.get("enabled", True):
        return [asdict(CheckResult("L1", "quality", "self_grading", "SKIP"))]

    max_happy_ratio = l1_conf.get("happy_path_ratio_max", 0.8)
    test_files = [f for f in files if "/tests/" in str(f) and f.name.startswith("test_")]

    if not test_files:
        return [asdict(CheckResult(
            "L1", "quality", "self_grading", "SKIP",
            details="No test files in changeset",
        ))]

    results = []
    for f in test_files:
        rel = str(f.relative_to(ROOT))
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue

        lines = content.splitlines()
        test_names = re.findall(r'(?:async\s+)?def\s+(test_\w+)', content)
        if not test_names:
            continue

        # Count negative/error test patterns
        negative_patterns = re.compile(
            r'test_(?:invalid|error|fail|reject|bad|missing|empty|none|'
            r'unauthorized|forbidden|timeout|not_found|duplicate|conflict|'
            r'malformed|corrupt|overflow|exceed)',
            re.IGNORECASE,
        )
        negative_tests = [t for t in test_names if negative_patterns.match(t)]

        # Count error-handling assertions
        error_assertions = sum(1 for ln in lines if re.search(
            r'pytest\.raises|assertRaises|assert.*[Ee]rror|assert.*[Ee]xception|'
            r'assert.*status_code\s*[!=]=\s*[45]\d\d|'
            r'assert.*fail|with\s+pytest\.warns',
            ln,
        ))

        # Calculate happy-path ratio
        total_tests = len(test_names)
        happy_only = total_tests - len(negative_tests)
        happy_ratio = happy_only / total_tests if total_tests > 0 else 1.0

        # Flag if both conditions met: high happy ratio AND no error assertions
        if happy_ratio > max_happy_ratio and error_assertions == 0:
            results.append(asdict(CheckResult(
                "L1", "quality", "self_grading", "WARN",
                details=(
                    f"Possible self-grading: {total_tests} tests, "
                    f"{len(negative_tests)} negative, "
                    f"{error_assertions} error assertions. "
                    f"Happy-path ratio: {happy_ratio:.0%} (max: {max_happy_ratio:.0%})"
                ),
                file=rel,
            )))

    if not results:
        results.append(asdict(CheckResult("L1", "quality", "self_grading", "PASS")))
    return results
