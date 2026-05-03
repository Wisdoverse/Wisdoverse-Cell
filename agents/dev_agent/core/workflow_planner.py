"""LLM-driven task to workflow JSON conversion."""
from __future__ import annotations

import json
import re
import time
from typing import Any

from shared.infra.llm_gateway import LLMGateway
from shared.utils.logger import get_logger

from ..app.metrics import LLM_CALL_DURATION, LLM_CALL_ERRORS
from ..models.schemas import SanitizedTask, WorkflowPlan
from .config import DevCoreConfig
from .prompts import WORKFLOW_PLANNER_SYSTEM

logger = get_logger("dev_agent.workflow_planner")

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(raw: str) -> dict[str, Any] | None:
    """Extract JSON object from raw LLM output.

    Handles plain JSON, markdown-fenced JSON, and JSON embedded in
    surrounding text.  Returns *None* when no valid JSON is found.
    """
    if not raw or not raw.strip():
        return None

    # 1. Try parsing the whole string as JSON
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown code fences
    fence_match = _FENCE_PATTERN.search(raw)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Try finding the first JSON object in the text
    obj_match = _JSON_OBJECT_PATTERN.search(raw)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def inject_project_id(plan: WorkflowPlan, project_id: str) -> WorkflowPlan:
    """Inject the configured AgentForge project ID into every node config."""
    normalized_project_id = project_id.strip()
    if not normalized_project_id:
        return plan

    for node in plan.nodes:
        node.config["projectId"] = normalized_project_id

    return plan


class WorkflowPlanner:
    """Convert a sanitized task into a WorkflowPlan via LLM."""

    def __init__(
        self,
        llm_gateway: LLMGateway,
        config: DevCoreConfig | None = None,
    ) -> None:
        self._llm = llm_gateway
        self._config = config or DevCoreConfig()

    async def plan(self, task: SanitizedTask) -> WorkflowPlan | None:
        """Generate a workflow plan from a task via LLM."""
        user_prompt = (
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Estimated hours: {task.estimated_hours}\n"
            f"Related files: {', '.join(task.related_files) or 'none specified'}\n"
            f"WP ID: {task.wp_id}"
        )

        start = time.monotonic()
        try:
            raw_text = await self._llm.complete(
                prompt=user_prompt,
                agent_id="dev-agent",
                task_type="workflow_planning",
                model=self._config.decompose_model,
                max_tokens=4096,
                temperature=0,
                system_prompt=WORKFLOW_PLANNER_SYSTEM,
            )
            elapsed = time.monotonic() - start
            LLM_CALL_DURATION.observe(elapsed)

            parsed = extract_json(raw_text)
            if parsed is None:
                LLM_CALL_ERRORS.inc()
                logger.warning("workflow_planner_parse_failed", raw_length=len(raw_text))
                return None

            return WorkflowPlan.model_validate(parsed)
        except Exception as e:
            elapsed = time.monotonic() - start
            LLM_CALL_DURATION.observe(elapsed)
            LLM_CALL_ERRORS.inc()
            logger.error(
                "workflow_planner_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return None
