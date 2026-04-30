#!/usr/bin/env bash
# Generate pinned dependency lock file from requirements.txt
# Run this in CI or before deployment to ensure reproducible builds
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if ! command -v pip-compile &>/dev/null; then
    echo "Installing pip-tools..."
    pip install pip-tools
fi

pip-compile requirements.txt -o requirements-lock.txt --strip-extras
echo "Lock file generated: requirements-lock.txt"
