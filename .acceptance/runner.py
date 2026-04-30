#!/usr/bin/env python3
"""
Acceptance Framework Runner
============================
Orchestrates L0/L1/L2 checks and produces a unified JSON report.

Usage:
    python .acceptance/runner.py [--target agents/pjm_agent] [--level l0] [--format json|markdown]
    python .acceptance/runner.py --diff HEAD~1   # Only check changed files
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    level: str  # L0, L1, L2
    category: str  # security, architecture, quality, ...
    check: str  # check name
    status: str  # PASS, FAIL, WARN, INFO, SKIP
    details: str | None = None
    file: str | None = None
    line: int | None = None


@dataclass
class AcceptanceReport:
    framework_version: str = "1.0"
    mr_id: str = ""
    timestamp: str = ""
    target: str = ""
    summary: dict = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0

    def add(self, result: CheckResult) -> None:
        self.results.append(asdict(result))

    def finalize(self) -> None:
        l0_fails = [r for r in self.results if r["level"] == "L0" and r["status"] == "FAIL"]
        l1_warns = [r for r in self.results if r["level"] == "L1" and r["status"] == "WARN"]
        self.summary = {
            "l0_gate": "FAIL" if l0_fails else "PASS",
            "l1_check": "WARN" if l1_warns else "PASS",
            "l2_report": "INFO",
            "total_checks": len(self.results),
            "l0_failures": len(l0_fails),
            "l1_warnings": len(l1_warns),
        }


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    """Load YAML config. Requires pyyaml — exits hard if unavailable."""
    try:
        import yaml
    except ImportError:
        print(
            "ERROR: pyyaml is required for acceptance checks. Install: pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"ERROR: Failed to load config {CONFIG_PATH}: {e}", file=sys.stderr)
        sys.exit(2)


def _get_changed_files(diff_ref: str | None) -> list[Path]:
    """Get list of changed .py files from git diff."""
    if not diff_ref:
        return []
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", diff_ref],
            cwd=ROOT,
            text=True,
        )
        return [ROOT / f for f in out.strip().splitlines() if f.endswith(".py")]
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"WARNING: git diff failed for ref '{diff_ref}': {e}", file=sys.stderr)
        return []


def _get_python_files(target: str) -> list[Path]:
    """Collect all .py files under target directory."""
    target_path = ROOT / target
    if not target_path.exists():
        return []
    if target_path.is_file():
        return [target_path]
    return sorted(target_path.rglob("*.py"))


def _get_agent_coverage_threshold(agent_name: str, config: dict) -> int:
    """Look up the coverage threshold for an agent based on its classification."""
    agent_types = config.get("agent_types", {})
    for _type_name, type_conf in agent_types.items():
        if agent_name in type_conf.get("agents", []):
            return type_conf.get("coverage_threshold", 60)
    return agent_types.get("default", {}).get("coverage_threshold", 60)


# ---------------------------------------------------------------------------
# L0 GATE checks
# ---------------------------------------------------------------------------


def check_hardcoded_secrets(files: list[Path], config: dict) -> list[CheckResult]:
    """Scan for hardcoded secrets using regex patterns."""
    results = []
    sec_conf = config.get("l0_gate", {}).get("security", {}).get("hardcoded_secrets", {})
    if not sec_conf.get("enabled", True):
        return [CheckResult("L0", "security", "hardcoded_secrets", "SKIP")]

    patterns = [re.compile(p) for p in sec_conf.get("patterns", [])]
    exclude = sec_conf.get("exclude_files", [])

    found = False
    for f in files:
        rel = str(f.relative_to(ROOT))
        if any(_match_glob(rel, ex) for ex in exclude):
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            for pat in patterns:
                if pat.search(line):
                    results.append(
                        CheckResult(
                            "L0",
                            "security",
                            "hardcoded_secrets",
                            "FAIL",
                            details=f"Potential secret detected (pattern: {pat.pattern[:40]})",
                            file=rel,
                            line=i,
                        )
                    )
                    found = True
    if not found:
        results.append(CheckResult("L0", "security", "hardcoded_secrets", "PASS"))
    return results


def check_sql_injection(files: list[Path], config: dict) -> list[CheckResult]:
    """Detect raw f-string SQL construction."""
    results = []
    sec_conf = config.get("l0_gate", {}).get("security", {}).get("sql_injection", {})
    if not sec_conf.get("enabled", True):
        return [CheckResult("L0", "security", "sql_injection", "SKIP")]

    patterns = [re.compile(p) for p in sec_conf.get("patterns", [])]
    exclude = sec_conf.get("exclude_files", [])

    found = False
    for f in files:
        rel = str(f.relative_to(ROOT))
        if any(_match_glob(rel, ex) for ex in exclude):
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            for pat in patterns:
                if pat.search(line):
                    results.append(
                        CheckResult(
                            "L0",
                            "security",
                            "sql_injection",
                            "FAIL",
                            details=f"Potential SQL injection: {line.strip()[:80]}",
                            file=rel,
                            line=i,
                        )
                    )
                    found = True
    if not found:
        results.append(CheckResult("L0", "security", "sql_injection", "PASS"))
    return results


def check_pii_in_logs(files: list[Path], config: dict) -> list[CheckResult]:
    """Detect PII fields in logger calls."""
    results = []
    sec_conf = config.get("l0_gate", {}).get("security", {}).get("pii_in_logs", {})
    if not sec_conf.get("enabled", True):
        return [CheckResult("L0", "security", "pii_in_logs", "SKIP")]

    patterns = [re.compile(p) for p in sec_conf.get("patterns", [])]
    safe_patterns = [re.compile(p) for p in sec_conf.get("safe_patterns", [])]
    exclude = sec_conf.get("exclude_files", [])

    found = False
    for f in files:
        rel = str(f.relative_to(ROOT))
        if any(_match_glob(rel, ex) for ex in exclude):
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            for pat in patterns:
                if pat.search(line):
                    # Skip if any safe pattern matches (e.g. bool(), string labels)
                    if any(sp.search(line) for sp in safe_patterns):
                        continue
                    results.append(
                        CheckResult(
                            "L0",
                            "security",
                            "pii_in_logs",
                            "FAIL",
                            details=f"PII in log: {line.strip()[:80]}",
                            file=rel,
                            line=i,
                        )
                    )
                    found = True
    if not found:
        results.append(CheckResult("L0", "security", "pii_in_logs", "PASS"))
    return results


def check_deprecated_imports(files: list[Path], config: dict) -> list[CheckResult]:
    """Block imports from deprecated shared.services.* paths."""
    results = []
    arch_conf = config.get("l0_gate", {}).get("architecture", {}).get("deprecated_imports", {})
    if not arch_conf.get("enabled", True):
        return [CheckResult("L0", "architecture", "deprecated_imports", "SKIP")]

    blocked = arch_conf.get("blocked_patterns", [])
    found = False
    for f in files:
        rel = str(f.relative_to(ROOT))
        # Don't check shared/services itself or tests
        if rel.startswith("shared/services") or rel.startswith(".acceptance"):
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            for pattern in blocked:
                if pattern in line:
                    results.append(
                        CheckResult(
                            "L0",
                            "architecture",
                            "deprecated_imports",
                            "FAIL",
                            details=f"Deprecated import: {line.strip()}",
                            file=rel,
                            line=i,
                        )
                    )
                    found = True
    if not found:
        results.append(CheckResult("L0", "architecture", "deprecated_imports", "PASS"))
    return results


def check_event_format(files: list[Path], config: dict) -> list[CheckResult]:
    """Ensure events use EventTypes constants, not raw strings."""
    results = []
    arch_conf = config.get("l0_gate", {}).get("architecture", {}).get("event_format", {})
    if not arch_conf.get("enabled", True):
        return [CheckResult("L0", "architecture", "event_format", "SKIP")]

    pattern = re.compile(r'event_type\s*=\s*["\x27][a-z]+\.[a-z]')
    allowed = arch_conf.get("allowed_files", [])

    found = False
    for f in files:
        rel = str(f.relative_to(ROOT))
        if any(_match_glob(rel, a) for a in allowed):
            continue
        # Test files may use fake event types for testing
        if "/tests/" in rel or rel.startswith("tests/"):
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                results.append(
                    CheckResult(
                        "L0",
                        "architecture",
                        "event_format",
                        "FAIL",
                        details=f"Raw event_type string, use EventTypes: {line.strip()[:60]}",
                        file=rel,
                        line=i,
                    )
                )
                found = True
    if not found:
        results.append(CheckResult("L0", "architecture", "event_format", "PASS"))
    return results


def check_base_agent_inheritance(files: list[Path], config: dict) -> list[CheckResult]:
    """Verify agent classes inherit BaseAgent."""
    results = []
    arch_conf = config.get("l0_gate", {}).get("architecture", {}).get("base_agent_required", {})
    if not arch_conf.get("enabled", True):
        return [CheckResult("L0", "architecture", "base_agent_required", "SKIP")]

    agent_files = [f for f in files if "/service/agent.py" in str(f) and "/agents/" in str(f)]
    if not agent_files:
        return [
            CheckResult(
                "L0",
                "architecture",
                "base_agent_required",
                "SKIP",
                details="No agent files in changeset",
            )
        ]

    class_pattern = re.compile(r"class\s+\w+Agent\s*\(")
    baseagent_pattern = re.compile(r"class\s+\w+Agent\s*\(\s*BaseAgent\s*\)")

    for f in agent_files:
        rel = str(f.relative_to(ROOT))
        content = f.read_text(errors="ignore")
        classes = class_pattern.findall(content)
        if classes and not baseagent_pattern.search(content):
            results.append(
                CheckResult(
                    "L0",
                    "architecture",
                    "base_agent_required",
                    "FAIL",
                    details="Agent class does not inherit BaseAgent",
                    file=rel,
                )
            )
        else:
            results.append(
                CheckResult(
                    "L0",
                    "architecture",
                    "base_agent_required",
                    "PASS",
                    file=rel,
                )
            )
    return results


def check_hallucinated_imports(files: list[Path], _config: dict) -> list[CheckResult]:
    """Verify all imports resolve to existing modules."""
    results = []
    import_pattern = re.compile(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")

    found = False
    for f in files:
        rel = str(f.relative_to(ROOT))
        if rel.startswith("tests/") or "/tests/" in rel:
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            line_stripped = line.strip()
            if line_stripped.startswith("#"):
                continue
            m = import_pattern.match(line_stripped)
            if not m:
                continue
            module = m.group(1) or m.group(2)
            if not module:
                continue
            # Only check project-internal imports
            if not (module.startswith("shared.") or module.startswith("agents.")):
                continue
            # Convert module path to filesystem path
            module_path = ROOT / module.replace(".", "/")
            if not (
                module_path.exists()
                or module_path.with_suffix(".py").exists()
                or (module_path / "__init__.py").exists()
            ):
                results.append(
                    CheckResult(
                        "L0",
                        "quality",
                        "hallucinated_imports",
                        "FAIL",
                        details=f"Import not found: {module}",
                        file=rel,
                        line=i,
                    )
                )
                found = True
    if not found:
        results.append(CheckResult("L0", "quality", "hallucinated_imports", "PASS"))
    return results


def check_ruff(files: list[Path], _config: dict) -> list[CheckResult]:
    """Run ruff check on changed files only."""
    py_files = [str(f) for f in files if f.suffix == ".py" and f.exists()]
    if not py_files:
        return [
            CheckResult("L0", "quality", "ruff_check", "SKIP", details="No Python files to check")
        ]
    try:
        result = subprocess.run(
            ["ruff", "check", *py_files, "--select", "E,F", "--ignore", "E501", "--no-fix", "--output-format", "json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60,
        )
        if result.returncode == 0:
            return [CheckResult("L0", "quality", "ruff_check", "PASS")]

        try:
            issues = json.loads(result.stdout)
        except json.JSONDecodeError:
            issues = []

        results = []
        for issue in issues[:20]:  # Cap at 20 to avoid flooding
            results.append(
                CheckResult(
                    "L0",
                    "quality",
                    "ruff_check",
                    "FAIL",
                    details=f"{issue.get('code', '?')}: {issue.get('message', '?')}",
                    file=issue.get("filename", ""),
                    line=issue.get("location", {}).get("row"),
                )
            )
        return results or [
            CheckResult("L0", "quality", "ruff_check", "FAIL", details=result.stderr[:200])
        ]
    except FileNotFoundError:
        return [CheckResult("L0", "quality", "ruff_check", "SKIP", details="ruff not installed")]
    except subprocess.TimeoutExpired:
        return [CheckResult("L0", "quality", "ruff_check", "FAIL", details="ruff timed out")]


def check_test_coverage(files: list[Path], config: dict) -> list[CheckResult]:
    """Check that changed agent code has corresponding tests.

    Discovers affected agents from the file list and verifies each has a
    tests/ directory. Does NOT run pytest (that's the unit-test CI job's
    responsibility) — this is a structural gate only.
    """
    # Discover which agents are touched by the changeset
    affected_agents: dict[str, Path] = {}
    for f in files:
        try:
            rel = f.relative_to(ROOT)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) >= 2 and parts[0] == "agents" and parts[1] != "__pycache__":
            agent_name = parts[1]
            if agent_name not in affected_agents:
                affected_agents[agent_name] = ROOT / "agents" / agent_name

    if not affected_agents:
        return [
            CheckResult(
                "L0", "quality", "test_exists", "SKIP", details="No agent code in changeset"
            )
        ]

    results = []
    for agent_name, agent_path in sorted(affected_agents.items()):
        test_dir = agent_path / "tests"
        if not test_dir.exists():
            results.append(
                CheckResult(
                    "L0",
                    "quality",
                    "test_exists",
                    "FAIL",
                    details=f"No tests/ directory in agents/{agent_name}",
                    file=f"agents/{agent_name}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "L0",
                    "quality",
                    "test_exists",
                    "PASS",
                    details=f"agents/{agent_name}/tests/ exists",
                    file=f"agents/{agent_name}",
                )
            )
    return results


# ---------------------------------------------------------------------------
# L1 CHECK checks
# ---------------------------------------------------------------------------


def check_test_quality(files: list[Path], config: dict) -> list[CheckResult]:
    """Analyze test assertion density and exception path coverage."""
    results = []
    l1_conf = config.get("l1_check", {}).get("test_quality", {})
    if not l1_conf.get("enabled", True):
        return [CheckResult("L1", "quality", "test_quality", "SKIP")]

    min_density = l1_conf.get("assertion_density_min", 2.0)
    test_files = [f for f in files if "/tests/" in str(f) and f.name.startswith("test_")]

    if not test_files:
        return [
            CheckResult(
                "L1", "quality", "test_quality", "SKIP", details="No test files in changeset"
            )
        ]

    for f in test_files:
        rel = str(f.relative_to(ROOT))
        content = f.read_text(errors="ignore")
        lines = content.splitlines()

        test_count = sum(1 for ln in lines if re.match(r"\s*(async\s+)?def\s+test_", ln))
        assert_count = sum(1 for ln in lines if re.search(r"\bassert\b|\.assert", ln))
        has_exception_test = bool(
            re.search(
                r"pytest\.raises|with.*Error|with.*Exception|assert.*error|assert.*fail",
                content,
                re.I,
            )
        )

        if test_count == 0:
            continue

        density = assert_count / test_count
        if density < min_density:
            results.append(
                CheckResult(
                    "L1",
                    "quality",
                    "test_quality",
                    "WARN",
                    details=f"Assertion density: {density:.1f}/test (min: {min_density})",
                    file=rel,
                )
            )
        if not has_exception_test:
            results.append(
                CheckResult(
                    "L1",
                    "quality",
                    "test_quality",
                    "WARN",
                    details="No exception/error path tests found",
                    file=rel,
                )
            )

    if not results:
        results.append(CheckResult("L1", "quality", "test_quality", "PASS"))
    return results


def check_over_engineering(files: list[Path], config: dict) -> list[CheckResult]:
    """Detect new abstract base classes, excessive class hierarchies, unused config."""
    results = []
    l1_conf = config.get("l1_check", {}).get("over_engineering", {})
    if not l1_conf.get("enabled", True):
        return [CheckResult("L1", "semantic", "over_engineering", "SKIP")]

    abc_pattern = re.compile(r"class\s+\w+\s*\(\s*(?:ABC|.*ABC.*)\s*\)")
    meta_pattern = re.compile(r"class\s+\w+\s*\(\s*(?:type|ABCMeta)\s*\)")

    for f in files:
        rel = str(f.relative_to(ROOT))
        if "/tests/" in rel or rel.startswith("shared/"):
            continue
        try:
            content = f.read_text(errors="ignore")
        except OSError:
            continue

        # Flag new ABCs in agent code (usually over-engineering)
        for i, line in enumerate(content.splitlines(), 1):
            if abc_pattern.search(line) or meta_pattern.search(line):
                results.append(
                    CheckResult(
                        "L1",
                        "semantic",
                        "over_engineering",
                        "WARN",
                        details=f"New ABC in agent code — verify in spec: {line.strip()[:60]}",
                        file=rel,
                        line=i,
                    )
                )

    if not results:
        results.append(CheckResult("L1", "semantic", "over_engineering", "PASS"))
    return results


# ---------------------------------------------------------------------------
# L2 REPORT checks
# ---------------------------------------------------------------------------


def report_complexity(files: list[Path], config: dict) -> list[CheckResult]:
    """Report functions exceeding complexity/length thresholds."""
    results = []
    l2_conf = config.get("l2_report", {}).get("complexity", {})
    if not l2_conf.get("enabled", True):
        return []

    max_length = l2_conf.get("function_length_max", 50)
    func_pattern = re.compile(r"^\s*(async\s+)?def\s+(\w+)\s*\(")

    for f in files:
        rel = str(f.relative_to(ROOT))
        if "/tests/" in rel:
            continue
        try:
            lines = f.read_text(errors="ignore").splitlines()
        except OSError:
            continue

        current_func = None
        func_start = 0

        for i, line in enumerate(lines, 1):
            m = func_pattern.match(line)
            if m:
                # Close previous function
                if current_func and (i - 1 - func_start) > max_length:
                    results.append(
                        CheckResult(
                            "L2",
                            "complexity",
                            "function_length",
                            "INFO",
                            details=f"{current_func}: {i - 1 - func_start} lines"
                            f" (limit {max_length})",
                            file=rel,
                            line=func_start,
                        )
                    )
                current_func = m.group(2)
                func_start = i
                _ = len(line) - len(line.lstrip())  # reserved for future use

        # Close last function
        if current_func and (len(lines) - func_start) > max_length:
            results.append(
                CheckResult(
                    "L2",
                    "complexity",
                    "function_length",
                    "INFO",
                    details=f"{current_func}: {len(lines) - func_start} lines (limit {max_length})",
                    file=rel,
                    line=func_start,
                )
            )
    return results


def report_ai_patterns(files: list[Path], config: dict) -> list[CheckResult]:
    """Detect AI-typical code patterns like excessive commenting."""
    results = []
    l2_conf = config.get("l2_report", {}).get("ai_patterns", {})
    if not l2_conf.get("enabled", True):
        return []

    max_ratio = l2_conf.get("comment_code_ratio_max", 0.4)

    for f in files:
        rel = str(f.relative_to(ROOT))
        if "/tests/" in rel:
            continue
        try:
            lines = f.read_text(errors="ignore").splitlines()
        except OSError:
            continue

        if len(lines) < 10:
            continue

        comment_lines = sum(
            1 for ln in lines if ln.strip().startswith("#") and not ln.strip().startswith("#!")
        )
        code_lines = sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))

        if code_lines == 0:
            continue

        ratio = comment_lines / code_lines
        if ratio > max_ratio:
            results.append(
                CheckResult(
                    "L2",
                    "ai_patterns",
                    "excessive_comments",
                    "INFO",
                    details=f"Comment/code ratio: {ratio:.2f} (max: {max_ratio}). Possibly AI-gen.",
                    file=rel,
                )
            )
    return results


# ---------------------------------------------------------------------------
# Glob helper
# ---------------------------------------------------------------------------


def _match_glob(path: str, pattern: str) -> bool:
    """Simple glob matching for exclude patterns."""
    import fnmatch

    return fnmatch.fnmatch(path, pattern)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_markdown(report: AcceptanceReport) -> str:
    """Format report as Markdown for MR comments."""
    lines = []
    gate = report.summary.get("l0_gate", "?")
    gate_emoji = "\u2705" if gate == "PASS" else "\u274c"
    lines.append(f"## {gate_emoji} Acceptance Report")
    lines.append("")
    lines.append(
        f"**L0 GATE**: {gate} | **L1 CHECK**: {report.summary.get('l1_check', '?')} | **L2**: INFO"
    )
    lines.append(f"**Target**: `{report.target}` | **Duration**: {report.duration_seconds:.1f}s")
    lines.append("")

    # Group by level
    for level, label in [
        ("L0", "L0 GATE (hard-block)"),
        ("L1", "L1 CHECK (review)"),
        ("L2", "L2 REPORT (info)"),
    ]:
        level_results = [r for r in report.results if r["level"] == level and r["status"] != "PASS"]
        if not level_results:
            continue
        lines.append(f"### {label}")
        lines.append("")
        for r in level_results:
            status_icon = {
                "FAIL": "\u274c",
                "WARN": "\u26a0\ufe0f",
                "INFO": "\u2139\ufe0f",
                "SKIP": "\u23ed\ufe0f",
            }.get(r["status"], "?")
            loc = (
                f"`{r['file']}:{r['line']}`"
                if r.get("file") and r.get("line")
                else (f"`{r['file']}`" if r.get("file") else "")
            )
            lines.append(f"- {status_icon} **{r['check']}**: {r.get('details', '')} {loc}")
        lines.append("")

    # Summary of passes
    passes = sum(1 for r in report.results if r["status"] == "PASS")
    lines.append("---")
    lines.append(f"*{passes}/{len(report.results)} checks passed*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(target: str, level: str, diff_ref: str | None, mr_id: str) -> AcceptanceReport:
    config = _load_config()
    report = AcceptanceReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        target=target,
        mr_id=mr_id,
    )
    start = time.monotonic()

    # Determine files to check
    if diff_ref:
        files = _get_changed_files(diff_ref)
    else:
        files = _get_python_files(target)

    if not files:
        report.add(
            CheckResult("L0", "meta", "file_collection", "SKIP", details="No Python files to check")
        )
        report.finalize()
        return report

    # L0 GATE
    if level in ("l0", "all"):
        report.results.extend([asdict(r) for r in check_hardcoded_secrets(files, config)])
        report.results.extend([asdict(r) for r in check_sql_injection(files, config)])
        report.results.extend([asdict(r) for r in check_pii_in_logs(files, config)])
        report.results.extend([asdict(r) for r in check_deprecated_imports(files, config)])
        report.results.extend([asdict(r) for r in check_event_format(files, config)])
        report.results.extend([asdict(r) for r in check_base_agent_inheritance(files, config)])
        report.results.extend([asdict(r) for r in check_hallucinated_imports(files, config)])
        report.results.extend([asdict(r) for r in check_ruff(files, config)])
        report.results.extend([asdict(r) for r in check_test_coverage(files, config)])

    # L1 CHECK
    if level in ("l1", "all"):
        report.results.extend([asdict(r) for r in check_test_quality(files, config)])
        report.results.extend([asdict(r) for r in check_over_engineering(files, config)])

        # LLM-powered checks (require ANTHROPIC_API_KEY)
        checks_dir = Path(__file__).resolve().parent / "checks"
        if str(checks_dir.parent) not in sys.path:
            sys.path.insert(0, str(checks_dir.parent))
        try:
            from checks.spec_drift import run_spec_drift_check

            report.results.extend(run_spec_drift_check(target, config))
        except Exception as e:
            report.add(CheckResult("L1", "semantic", "spec_drift", "SKIP", details=f"Error: {e}"))

        try:
            from checks.self_grading import check_self_grading

            report.results.extend(check_self_grading(files, config))
        except Exception as e:
            report.add(CheckResult("L1", "quality", "self_grading", "SKIP", details=f"Error: {e}"))

    # L2 REPORT
    if level in ("l2", "all"):
        report.results.extend([asdict(r) for r in report_complexity(files, config)])
        report.results.extend([asdict(r) for r in report_ai_patterns(files, config)])

    report.duration_seconds = time.monotonic() - start
    report.finalize()
    return report


def main():
    parser = argparse.ArgumentParser(description="Acceptance Framework Runner")
    parser.add_argument("--target", default="agents/", help="Directory or file to check")
    parser.add_argument("--level", choices=["l0", "l1", "l2", "all"], default="all")
    parser.add_argument("--diff", default=None, help="Git diff ref (e.g. HEAD~1, origin/main)")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--mr-id", default="", help="MR identifier for report")
    parser.add_argument("--output", default=None, help="Output file path (default: stdout)")
    args = parser.parse_args()

    report = run(args.target, args.level, args.diff, args.mr_id)

    if args.format == "json":
        output = json.dumps(asdict(report), indent=2, ensure_ascii=False)
    else:
        output = format_markdown(report)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Exit code: non-zero if L0 failed
    if report.summary.get("l0_gate") == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
