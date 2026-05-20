#!/usr/bin/env bash
# Migration progress metrics — run in CI or manually
set -euo pipefail

echo "=== Migration Progress ==="
OLD=$(grep -rnE '(from|import) shared\.services(\.|\s|$)|(from|import) skills(\.|\s|$)' --include='*.py' | wc -l || true)
NEW=$(grep -rn 'from shared\.\(core\|messaging\|integrations\|infra\)' --include='*.py' | wc -l || true)
COMPAT=$(( $(find shared/services -name '*.py' 2>/dev/null | wc -l || true) + $(find skills -name '*.py' 2>/dev/null | wc -l || true) ))
PATCH_STR=$(grep -rn 'patch("shared\.' --include='*.py' | wc -l || true)

echo "old_import_count=$OLD"
echo "new_import_count=$NEW"
echo "retired_compat_layer_files=$COMPAT"
echo "patch_string_count=$PATCH_STR"
