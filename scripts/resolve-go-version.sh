#!/usr/bin/env bash
# Resolve the latest Go patch version from Go download API.
# Falls back to a pinned version if the API is unreachable.
#
# Usage: resolve-go-version.sh <major.minor> <fallback> [base-url]
# Example: resolve-go-version.sh 1.25 go1.25.8
#   → prints "go1.25.8" (latest) or fallback on failure
#
# CN usage: resolve-go-version.sh 1.25 go1.25.8 https://golang.google.cn/dl
#   → queries golang.google.cn instead of go.dev

set -euo pipefail

GO_MINOR="${1:?Usage: resolve-go-version.sh <major.minor> <fallback> [base-url]}"
FALLBACK="${2:?Usage: resolve-go-version.sh <major.minor> <fallback> [base-url]}"
BASE_URL="${3:-https://go.dev/dl}"

RESOLVED=$(
  curl -sSL --retry 3 --retry-delay 2 --retry-all-errors \
    "${BASE_URL}/?mode=json" 2>/dev/null \
  | python3 -c "
import json, sys
try:
    versions = json.load(sys.stdin)
    matches = [v['version'] for v in versions if v['version'].startswith('go${GO_MINOR}')]
    print(matches[0] if matches else '')
except Exception:
    print('')
" 2>/dev/null
) || true

echo "${RESOLVED:-$FALLBACK}"
