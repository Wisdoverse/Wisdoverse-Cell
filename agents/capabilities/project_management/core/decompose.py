"""Task decomposition service using LLM."""

import json
import re

from shared.config import settings
from shared.infra.llm_gateway import LLMGateway
from shared.utils.logger import get_logger

from ..models.schemas import TaskCheckResult, WBSResult
from .prompts import (
    DECOMPOSE_SYSTEM_PROMPT,
    TASK_CHECK_SYSTEM_PROMPT,
    build_decompose_prompt,
    build_task_check_prompt,
)

logger = get_logger("pjm_agent.decompose")


class DecomposeError(Exception):
    """Raised when decomposition fails after retries."""


class DecomposeService:
    def __init__(self, llm_gateway: LLMGateway):
        self._llm = llm_gateway

    async def decompose(
        self,
        wp_id: int,
        subject: str,
        description: str,
        wp_type: str,
        project_name: str = "",
        assignee: str = "",
    ) -> WBSResult:
        prompt = build_decompose_prompt(
            subject=subject,
            description=description,
            wp_type=wp_type,
            project_name=project_name,
            assignee=assignee,
        )

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = await self._llm.complete(
                    prompt=prompt,
                    agent_id="pjm-agent",
                    task_type="decompose",
                    model=settings.decompose_model,
                    system_prompt=DECOMPOSE_SYSTEM_PROMPT,
                    max_tokens=4096,
                    temperature=0,
                )
                result = self._parse_response(raw)
                logger.info(
                    "decompose_ok",
                    wp_id=wp_id,
                    stories=len(result.subtasks),
                    tasks=sum(len(s.children) for s in result.subtasks),
                )
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "decompose_attempt_failed",
                    wp_id=wp_id,
                    attempt=attempt + 1,
                    error=str(e),
                )

        raise DecomposeError(f"Decomposition failed for wp_id={wp_id}: {last_error}")

    @staticmethod
    def _parse_response(raw: str) -> WBSResult:
        text = raw.strip()
        # Strip markdown code fences if present
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        data = json.loads(text)
        return WBSResult.model_validate(data)

    async def check_task_detail(
        self,
        wp_id: int,
        subject: str,
        description: str,
        project_name: str = "",
        assignee: str = "",
    ) -> TaskCheckResult:
        prompt = build_task_check_prompt(
            subject=subject,
            description=description,
            project_name=project_name,
            assignee=assignee,
        )

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = await self._llm.complete(
                    prompt=prompt,
                    agent_id="pjm-agent",
                    task_type="task_check",
                    model=settings.decompose_model,
                    system_prompt=TASK_CHECK_SYSTEM_PROMPT,
                    max_tokens=4096,
                    temperature=0,
                )
                result = self._parse_task_check_response(raw)
                logger.info(
                    "task_check_ok",
                    wp_id=wp_id,
                    detailed=result.detailed,
                    subtask_count=len(result.subtasks),
                )
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "task_check_attempt_failed",
                    wp_id=wp_id,
                    attempt=attempt + 1,
                    error=str(e),
                )

        raise DecomposeError(f"Task check failed for wp_id={wp_id}: {last_error}")

    @staticmethod
    def _parse_task_check_response(raw: str) -> TaskCheckResult:
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        data = json.loads(text)
        return TaskCheckResult.model_validate(data)
