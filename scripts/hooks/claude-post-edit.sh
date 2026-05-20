#!/usr/bin/env bash
# Claude Code PostToolUse hook: check edited Python files for retired imports
# Receives TOOL_INPUT as env var with JSON of the tool input

set -euo pipefail

# Extract file path from tool input
FILE_PATH=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_path',''))" 2>/dev/null || true)

# Only check Python files
[[ "$FILE_PATH" != *.py ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

# Inline check: scan the edited file for retired compatibility imports
if grep -qE '(from|import)\s+(shared\.services|skills)(\.|\s|$)' "$FILE_PATH" 2>/dev/null; then
  echo "⚠️  Retired compatibility import detected in $FILE_PATH — use canonical paths (shared.integrations.*, shared.messaging.*, shared.infra.*, agents.requirement_manager.skills.*)"
  exit 1
fi

if grep -qE '((from|import)\s+shared\.grpc\.server(\s|$)|from\s+shared\.grpc\s+import\s+.*\bserver\b)' "$FILE_PATH" 2>/dev/null; then
  echo "⚠️  Retired gRPC runtime import detected in $FILE_PATH — use agents.requirement_manager.grpc.server"
  exit 1
fi

exit 0
