#!/usr/bin/env bash
# Claude Code PostToolUse hook: check edited Python files for deprecated imports
# Receives TOOL_INPUT as env var with JSON of the tool input

set -euo pipefail

# Extract file path from tool input
FILE_PATH=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_path',''))" 2>/dev/null || true)

# Only check Python files
[[ "$FILE_PATH" != *.py ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

# Inline check: scan the edited file for deprecated shared.services.* imports
if grep -qE '(from|import)\s+shared\.services\.(gateway|channel_gateway|feishu|wecom|openclaw|openproject|channels|circuit_breaker|agent_client)\b' "$FILE_PATH" 2>/dev/null; then
  # Skip allowlisted compat stubs
  case "$FILE_PATH" in
    */shared/services/*) exit 0 ;;
  esac
  echo "⚠️  Deprecated import detected in $FILE_PATH — use canonical paths (shared.integrations.*, shared.messaging.*, shared.infra.*)"
  exit 1
fi

exit 0
