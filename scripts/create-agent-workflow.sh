#!/usr/bin/env bash
# =============================================================================
# Create and run an agent-development workflow via AgentForge Orchestrator
# =============================================================================
#
# Usage:
#   ./scripts/create-agent-workflow.sh <agent_name>
#   ./scripts/create-agent-workflow.sh notification_agent
#
# Prerequisites:
#   - AgentForge orchestrator running (default: http://localhost:4010)
#   - AGENTFORGE_API_URL and AGENTFORGE_TOKEN env vars (or defaults)
#
# What happens:
#   1. Reads workflow template from docs/workflows/agent-development.json
#   2. Substitutes ${AGENT_NAME} with the provided agent name
#   3. Creates the workflow via POST /api/v1/workflows
#   4. Runs the workflow via POST /api/v1/workflows/:id/run
#   5. Prints status URL for monitoring
#
# =============================================================================

set -euo pipefail

AGENT_NAME="${1:?Usage: $0 <agent_name>}"
API_URL="${AGENTFORGE_API_URL:-http://localhost:4010}"
TOKEN="${AGENTFORGE_TOKEN:-}"
TEMPLATE="docs/workflows/agent-development.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# Check spec exists
SPEC_FILE="docs/specs/${AGENT_NAME}.md"
if [ ! -f "$SPEC_FILE" ]; then
    echo "ERROR: Spec file not found: $SPEC_FILE"
    echo "Write a spec first: /write-spec or manually create docs/specs/${AGENT_NAME}.md"
    exit 1
fi

echo "=== AgentForge AI Team Workflow ==="
echo "Agent:    ${AGENT_NAME}"
echo "Spec:     ${SPEC_FILE}"
echo "API:      ${API_URL}"
echo ""

# Substitute AGENT_NAME in template
PAYLOAD=$(sed "s/\${AGENT_NAME}/${AGENT_NAME}/g" "$TEMPLATE")

# Auth header
AUTH_HEADER=""
if [ -n "$TOKEN" ]; then
    AUTH_HEADER="-H \"Authorization: Bearer ${TOKEN}\""
fi

# Step 1: Create workflow
echo ">>> Creating workflow..."
CREATE_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/workflows" \
    -H "Content-Type: application/json" \
    ${AUTH_HEADER:+-H "Authorization: Bearer ${TOKEN}"} \
    -d "$PAYLOAD")

WORKFLOW_ID=$(echo "$CREATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('workflow',{}).get('id',''))" 2>/dev/null)

if [ -z "$WORKFLOW_ID" ]; then
    echo "ERROR: Failed to create workflow"
    echo "$CREATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CREATE_RESPONSE"
    exit 1
fi

echo "    Workflow ID: ${WORKFLOW_ID}"

# Step 2: Run workflow
echo ">>> Starting workflow execution..."
RUN_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/workflows/${WORKFLOW_ID}/run" \
    -H "Content-Type: application/json" \
    ${AUTH_HEADER:+-H "Authorization: Bearer ${TOKEN}"})

RUN_STATUS=$(echo "$RUN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)

if [ "$RUN_STATUS" != "started" ]; then
    echo "ERROR: Failed to start workflow"
    echo "$RUN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RUN_RESPONSE"
    exit 1
fi

echo "    Status: started"
echo ""
echo "=== Workflow Running ==="
echo ""
echo "Monitor:  ${API_URL}/api/v1/workflows/${WORKFLOW_ID}/status"
echo ""
echo "Execution order:"
echo "  Layer 0: [plan]                          ← Codex 做实现计划"
echo "  Layer 1: [impl-contracts]                ← Claude Code 做契约/配置"
echo "  Layer 2: [impl-core, impl-parallel]      ← Claude Code + Gemini CLI 并行"
echo "  Layer 3: [review, acceptance]            ← Codex Review + 验收框架"
echo "  Layer 4: [fix]                           ← Claude Code 修复"
echo "  Layer 5: [packaging]                     ← Claude Code 打包"
echo "  Layer 6: [human-review]                  ← 等待你审批"
echo ""
echo "When human-review is reached, approve with:"
echo "  curl -X POST ${API_URL}/api/v1/workflows/${WORKFLOW_ID}/signal \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"nodeId\": \"<NODE_ID>\", \"decision\": \"approve\"}'"
echo ""
echo "Check status:"
echo "  curl -s ${API_URL}/api/v1/workflows/${WORKFLOW_ID}/status | python3 -m json.tool"
