#!/usr/bin/env bash
set -euo pipefail

if command -v pip-audit >/dev/null 2>&1; then
  pip_audit=(pip-audit)
else
  pip_audit=(python -m pip_audit)
fi

# Accepted no-fix advisories as of 2026-05-20.
#
# These IDs currently have no fix versions in the PyPI advisory feed. Keep this
# list explicit so new advisories still fail CI and accepted-risk entries are
# visible during architecture/security review.
ignored_vulns=(
  # transformers: checkpoint conversion / model conversion RCE advisories.
  # Runtime policy: do not load untrusted model code or conversion artifacts.
  PYSEC-2025-211
  PYSEC-2025-212
  PYSEC-2025-213
  PYSEC-2025-214
  PYSEC-2025-215
  PYSEC-2025-216
  PYSEC-2025-217
  PYSEC-2025-218

  # langchain-community TFIDFRetriever.load_local deserialization advisory.
  # Runtime policy: do not load untrusted retriever artifacts.
  PYSEC-2024-278

  # PyJWT weak-key advisory disputed by supplier; application owns key policy.
  PYSEC-2025-183

  # joblib pickle deserialization advisory disputed by supplier.
  # Runtime policy: do not load untrusted joblib artifacts.
  PYSEC-2024-277

  # torch local memory-corruption / deserialization / DoS advisories with no
  # published fixed version in the PyPI advisory feed.
  PYSEC-2025-189
  PYSEC-2025-190
  PYSEC-2025-191
  PYSEC-2025-192
  PYSEC-2025-193
  PYSEC-2025-194
  PYSEC-2025-195
  PYSEC-2025-196
  PYSEC-2025-197
  PYSEC-2025-210
  PYSEC-2026-139
)

ignore_args=()
for vuln_id in "${ignored_vulns[@]}"; do
  ignore_args+=(--ignore-vuln "${vuln_id}")
done

"${pip_audit[@]}" "${ignore_args[@]}" -r requirements.txt
"${pip_audit[@]}" "${ignore_args[@]}" -r requirements-lock.txt
