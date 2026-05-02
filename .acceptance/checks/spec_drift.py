"""
L1 CHECK: Spec Drift Detection
================================
Uses LLM to compare implementation code against spec documents.
Detects:
  - Features implemented but not in spec (scope creep)
  - Features in spec but not implemented (missing functionality)
  - Semantic divergence between spec intent and actual behavior
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Spec search locations (ordered by priority)
SPEC_DIRS = [
    ROOT / "docs" / "specs",
    ROOT / "docs" / "plans",
]


def find_spec_for_target(target: str) -> Path | None:
    """Find the most relevant spec document for a target agent/module."""
    # Extract agent name from target path like "agents/capabilities/project_management"
    parts = target.strip("/").split("/")
    agent_name = parts[1] if len(parts) > 1 and parts[0] == "agents" else parts[-1]

    # Normalize: pjm_agent -> pm, requirement_manager -> requirement
    search_terms = [
        agent_name,
        agent_name.replace("_agent", ""),
        agent_name.replace("_", "-"),
        agent_name.replace("_agent", "").replace("_", "-"),
    ]

    candidates = []
    for spec_dir in SPEC_DIRS:
        if not spec_dir.exists():
            continue
        for f in spec_dir.iterdir():
            if not f.suffix == ".md":
                continue
            fname_lower = f.stem.lower()
            for term in search_terms:
                if term in fname_lower:
                    candidates.append(f)
                    break

    if not candidates:
        return None

    # Prefer specs/ over plans/, and newer files over older ones
    def sort_key(p: Path) -> tuple:
        in_specs = 1 if "specs" in str(p) else 0
        return (in_specs, p.stat().st_mtime)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def collect_implementation_summary(target: str, max_chars: int = 12000) -> str:
    """Collect a summary of the implementation for LLM analysis."""
    target_path = ROOT / target
    if not target_path.exists():
        return ""

    parts = []
    total = 0

    # Priority files: agent.py, main.py, then services
    priority_globs = [
        "service/agent.py",
        "app/main.py",
        "core/*.py",
        "api/*.py",
        "models/schemas.py",
    ]

    seen = set()
    for pattern in priority_globs:
        for f in sorted(target_path.glob(pattern)):
            if f in seen or f.name == "__init__.py":
                continue
            seen.add(f)
            content = f.read_text(errors="ignore")
            header = f"### {f.relative_to(target_path)}\n"
            chunk = header + content
            if total + len(chunk) > max_chars:
                remaining = max_chars - total
                if remaining > 500:
                    parts.append(header + content[:remaining] + "\n[...truncated]")
                break
            parts.append(chunk)
            total += len(chunk)

    return "\n\n".join(parts)


def analyze_spec_drift(
    spec_content: str,
    impl_summary: str,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Use LLM to compare spec vs implementation and detect drift.

    Supports multiple providers via llm_client:
    Anthropic, OpenAI, Gemini, OpenRouter, Ollama.
    Auto-detects from environment variables.
    """
    from .llm_client import complete, parse_json_response

    system = "You are a senior QA engineer reviewing spec-vs-implementation alignment."

    prompt = f"""Compare this specification against the implementation code.

## Spec Document
{spec_content[:8000]}

## Implementation Code
{impl_summary[:12000]}

Return a JSON object:

{{
  "alignment_score": 0.0-1.0,
  "missing_from_impl": [
    {{"feature": "...", "severity": "high|medium|low", "spec_ref": "..."}}
  ],
  "not_in_spec": [
    {{"feature": "...", "severity": "high|medium|low", "file": "..."}}
  ],
  "semantic_drift": [
    {{"description": "...", "spec_says": "...", "impl_does": "...", "severity": "high|medium|low"}}
  ],
  "summary": "One paragraph summary"
}}

Rules:
- Only flag genuine mismatches, not implementation details the spec leaves open
- alignment_score 1.0 = perfect match
- Return ONLY valid JSON, no markdown fences"""

    try:
        resp = complete(prompt, system=system, model=model, provider=provider)
        return parse_json_response(resp.text)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"LLM analysis failed: {e}"}


def run_spec_drift_check(target: str, config: dict) -> list[dict]:
    """Run spec drift detection and return CheckResult-compatible dicts."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from runner import CheckResult

    l1_conf = config.get("l1_check", {}).get("spec_drift", {})
    if not l1_conf.get("enabled", True):
        return [CheckResult("L1", "semantic", "spec_drift", "SKIP").__dict__]

    threshold = l1_conf.get("threshold", 0.7)
    model = l1_conf.get("llm_model") or None  # None = auto-detect
    provider = l1_conf.get("llm_provider") or None  # None = auto-detect

    # Find spec
    spec_path = find_spec_for_target(target)
    if not spec_path:
        return [
            CheckResult(
                "L1",
                "semantic",
                "spec_drift",
                "SKIP",
                details=f"No spec document found for {target}",
            ).__dict__
        ]

    spec_content = spec_path.read_text(errors="ignore")
    impl_summary = collect_implementation_summary(target)

    if not impl_summary:
        return [
            CheckResult(
                "L1",
                "semantic",
                "spec_drift",
                "SKIP",
                details=f"No implementation code found in {target}",
            ).__dict__
        ]

    # Run LLM analysis
    result = analyze_spec_drift(spec_content, impl_summary, model=model, provider=provider)

    if "error" in result:
        return [
            CheckResult(
                "L1",
                "semantic",
                "spec_drift",
                "SKIP",
                details=result["error"],
            ).__dict__
        ]

    results = []
    score = result.get("alignment_score", 0)

    # Overall alignment
    if score < threshold:
        results.append(
            CheckResult(
                "L1",
                "semantic",
                "spec_drift",
                "WARN",
                details=(
                    f"Alignment score: {score:.2f} (threshold: {threshold}). "
                    f"{result.get('summary', '')}"
                ),
                file=str(spec_path.relative_to(ROOT)),
            ).__dict__
        )

    # Missing features
    for item in result.get("missing_from_impl", []):
        if item.get("severity") in ("high", "medium"):
            results.append(
                CheckResult(
                    "L1",
                    "semantic",
                    "spec_drift_missing",
                    "WARN",
                    details=f"Spec requires but not implemented: {item['feature']}",
                    file=str(spec_path.relative_to(ROOT)),
                ).__dict__
            )

    # Scope creep
    for item in result.get("not_in_spec", []):
        if item.get("severity") in ("high", "medium"):
            results.append(
                CheckResult(
                    "L1",
                    "semantic",
                    "spec_drift_extra",
                    "WARN",
                    details=f"Implemented but not in spec: {item['feature']}",
                    file=item.get("file", ""),
                ).__dict__
            )

    # Semantic drift
    for item in result.get("semantic_drift", []):
        if item.get("severity") in ("high", "medium"):
            results.append(
                CheckResult(
                    "L1",
                    "semantic",
                    "spec_drift_semantic",
                    "WARN",
                    details=(
                        f"{item['description']}. "
                        f"Spec: {item.get('spec_says', '')}. "
                        f"Impl: {item.get('impl_does', '')}"
                    ),
                ).__dict__
            )

    if not results:
        results.append(
            CheckResult(
                "L1",
                "semantic",
                "spec_drift",
                "PASS",
                details=f"Alignment score: {score:.2f}. {result.get('summary', '')}",
            ).__dict__
        )

    return results
