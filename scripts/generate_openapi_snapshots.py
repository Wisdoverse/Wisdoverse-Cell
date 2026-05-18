"""Generate per-runtime OpenAPI snapshots.

Stage 4 pre-condition per docs/architecture/migration-plan.md
§Stage 4 ("Publish per-agent OpenAPI snapshot; lock contract").
Stage 1 PR-template architecture-review checklist requires a snapshot
diff in every PR that changes a route.

Run:
    python scripts/generate_openapi_snapshots.py

Or via make:
    make openapi-snapshots

Writes one JSON file per runtime under docs/api/openapi/. Commit the
result. Snapshot diffs in PR review surface route or schema changes
before they reach production.

Design notes:
- Pure read of `app.openapi()`; no network or DB calls happen at
  schema generation time.
- `CONTROL_PLANE_ENABLED=false` is forced so the optional
  control-plane router does not bloat per-agent snapshots; the
  control plane has its own ledger surface already documented in
  `docs/guides/api-reference.md` §Control Plane API.
- Output is canonicalised (`sort_keys=True`, 2-space indent, trailing
  newline) so diffs are stable across runs.
"""

from __future__ import annotations

import json
import os
import sys
from importlib import import_module
from pathlib import Path

# Allow running from repo root via `python scripts/...`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

RUNTIMES: tuple[tuple[str, str], ...] = (
    ("agents.qa_agent.app.main", "qa-agent"),
    ("agents.pjm_agent.app.main", "pjm-agent"),
    ("agents.dev_agent.app.main", "dev-agent"),
    ("agents.requirement_manager.app.main", "requirement-manager"),
)

OUTPUT_DIR = Path("docs/api/openapi")


def _generate(module_path: str, runtime: str, out_dir: Path) -> Path:
    module = import_module(module_path)
    app = module.app
    schema = app.openapi()
    out_path = out_dir / f"{runtime}-v1.json"
    out_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    os.environ.setdefault("CONTROL_PLANE_ENABLED", "false")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for module_path, runtime in RUNTIMES:
        try:
            written = _generate(module_path, runtime, OUTPUT_DIR)
            print(f"wrote {written}", file=sys.stderr)
        except Exception as exc:
            failures.append(f"{runtime}: {type(exc).__name__}: {exc}")
            print(f"FAIL {runtime}: {exc}", file=sys.stderr)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
