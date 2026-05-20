#!/usr/bin/env python3
"""CI lint: Block code from importing retired compatibility paths.

Scans changed Python files for imports from retired module paths
(``shared.services.*`` and root ``skills.*``) that should use canonical
paths instead.

Exit code 0 = clean, 1 = violations found.
"""
import re
import subprocess
import sys

# Retired import paths -> canonical replacement
DEPRECATED_PATTERNS: list[tuple[str, str]] = [
    (r"from\s+shared\.services(?:\.|\s|$)", "canonical shared.* paths"),
    (r"import\s+shared\.services(?:\.|\s|$)", "canonical shared.* paths"),
    (r"from\s+skills(?:\.|\s|$)", "agents.requirement_manager.skills"),
    (r"import\s+skills(?:\.|\s|$)", "agents.requirement_manager.skills"),
    (r"from\s+shared\.services\.gateway\b", "shared.messaging.inbound"),
    (r"from\s+shared\.services\.channel_gateway\b", "shared.messaging.outbound"),
    (r"from\s+shared\.services\.feishu\b", "shared.integrations.feishu"),
    (r"from\s+shared\.services\.wecom\b", "shared.integrations.wecom"),
    (r"from\s+shared\.services\.openclaw\b", "shared.integrations.openclaw"),
    (r"from\s+shared\.services\.openproject\b", "shared.integrations.openproject"),
    (r"from\s+shared\.services\.channels\b", "shared.integrations.channels"),
    (r"from\s+shared\.services\.circuit_breaker\b", "shared.infra.circuit_breaker"),
    (r"from\s+shared\.services\.agent_client\b", "shared.infra.agent_client"),
    (r"import\s+shared\.services\.gateway\b", "shared.messaging.inbound"),
    (r"import\s+shared\.services\.channel_gateway\b", "shared.messaging.outbound"),
    (r"import\s+shared\.services\.feishu\b", "shared.integrations.feishu"),
    (r"import\s+shared\.services\.wecom\b", "shared.integrations.wecom"),
    (r"import\s+shared\.services\.openclaw\b", "shared.integrations.openclaw"),
    (r"import\s+shared\.services\.openproject\b", "shared.integrations.openproject"),
    (r"import\s+shared\.services\.channels\b", "shared.integrations.channels"),
    (r"import\s+shared\.services\.circuit_breaker\b", "shared.infra.circuit_breaker"),
    (r"import\s+shared\.services\.agent_client\b", "shared.infra.agent_client"),
]

def get_changed_files(target_branch: str | None = None) -> list[str]:
    """Get Python files changed vs target branch, or all tracked .py files."""
    if target_branch:
        cmd = [
            "git", "diff", "--name-only", "--diff-filter=d",
            f"origin/{target_branch}...HEAD", "--", "*.py",
        ]
    else:
        cmd = ["git", "ls-files", "--", "*.py"]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return [f for f in result.stdout.strip().split("\n") if f]


def scan_file(filepath: str) -> list[tuple[int, str, str]]:
    """Return list of (line_number, line, canonical_path) violations."""
    violations = []
    try:
        with open(filepath) as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern, canonical in DEPRECATED_PATTERNS:
                    if re.search(pattern, stripped):
                        violations.append((i, stripped, canonical))
                        break
    except (OSError, UnicodeDecodeError):
        pass
    return violations


def main() -> int:
    target_branch = sys.argv[1] if len(sys.argv) > 1 else None
    files = get_changed_files(target_branch)

    total_violations = 0
    for filepath in files:
        violations = scan_file(filepath)
        for line_no, line, canonical in violations:
            print(f"  {filepath}:{line_no}: {line}")
            print(f"    → Use: {canonical}")
            total_violations += 1

    if total_violations > 0:
        print(f"\n❌ {total_violations} retired compatibility import(s) found.")
        print("Use canonical paths instead of shared.services.* or root skills.*.")
        return 1

    print("✅ No retired compatibility imports found in changed files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
