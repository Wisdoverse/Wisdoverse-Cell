#!/usr/bin/env bash
# Claude Code PreToolUse hook: lint before git commit
# Blocks the commit if ruff finds errors in staged Python files

set -euo pipefail

# Only trigger on git commit commands
COMMAND=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('command',''))" 2>/dev/null || true)
echo "$COMMAND" | grep -q "git commit" || exit 0

# Get staged Python files
STAGED=$(git diff --cached --name-only --diff-filter=d -- '*.py' 2>/dev/null || true)
[[ -z "$STAGED" ]] && exit 0

# Run ruff on staged files only
echo "$STAGED" | xargs ruff check --quiet 2>/dev/null
