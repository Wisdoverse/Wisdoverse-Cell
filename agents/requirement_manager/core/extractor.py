"""Requirement extraction core logic."""

from pathlib import Path
from typing import Optional, Protocol

from pydantic import BaseModel

from shared.infra.prompt_boundaries import wrap_untrusted_json
from shared.utils.logger import get_logger

from .llm_extraction_response import LLMExtractionResponse

logger = get_logger("extractor")

_DEFAULT_SYSTEM_PROMPT = (
    "You are a professional product requirements analyst. "
    "You are skilled at extracting structured requirements from meeting notes."
)


class ExtractedRequirement(BaseModel):
    """Extracted requirement structure."""
    title: str
    description: str
    category: str = "功能"
    priority: str = "medium"
    source_quote: Optional[str] = None


class ExtractedDecision(BaseModel):
    """Extracted decision."""
    content: str
    decided_by: Optional[str] = None


class ExtractedQuestion(BaseModel):
    """Extracted open question."""
    question: str
    context: Optional[str] = None


class ExtractionResult(BaseModel):
    """Extraction result."""
    requirements: list[ExtractedRequirement] = []
    decisions: list[ExtractedDecision] = []
    open_questions: list[ExtractedQuestion] = []


class RequirementExtractionLLM(Protocol):
    async def complete(
        self,
        *,
        prompt: str,
        agent_id: str,
        task_type: str,
        temperature: float = 0,
        system_prompt: str | None = None,
    ) -> str:
        """Complete a requirement-extraction prompt."""


class SystemPromptResolver(Protocol):
    async def __call__(self, agent_id: str, default_prompt: str) -> str:
        """Resolve the deployed system prompt for an agent."""


def build_extraction_prompt(
    prompt_template: str,
    *,
    content: str,
    source: str,
    meeting_date: Optional[str],
    participants: Optional[list[str]],
    context: Optional[str],
) -> str:
    """Build the extraction prompt with source meeting data isolated."""
    meeting_notes_block = wrap_untrusted_json(
        "untrusted_meeting_notes_json",
        {"content": content},
    )
    context_block = wrap_untrusted_json(
        "untrusted_meeting_context_json",
        {
            "source": source,
            "meeting_date": meeting_date or "未知",
            "participants": ", ".join(participants) if participants else "未知",
            "context": context or "无",
        },
    )
    return prompt_template.format(
        meeting_notes_block=meeting_notes_block,
        context_block=context_block,
    )


class RequirementExtractor:
    """
    Requirement extractor.

    Uses the LLM Gateway to extract from meeting records:
    - Structured requirements
    - Decisions
    - Open questions
    """

    def __init__(
        self,
        *,
        llm: RequirementExtractionLLM,
        system_prompt_resolver: SystemPromptResolver,
        prompt_template: str | None = None,
    ):
        self._llm = llm
        self._system_prompt_resolver = system_prompt_resolver

        # Load the prompt template.
        if prompt_template is None:
            prompt_path = Path(__file__).parent.parent / "prompts" / "extract_requirements.md"
            prompt_template = prompt_path.read_text(encoding="utf-8")
        self.prompt_template = prompt_template

    async def extract(
        self,
        content: str,
        source: str = "upload",
        meeting_date: Optional[str] = None,
        participants: Optional[list[str]] = None,
        context: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract requirements from meeting content.

        Args:
            content: Meeting content text.
            source: Source channel (feishu/upload/wechat).
            meeting_date: Meeting date.
            participants: Participant list.
            context: Additional context notes.

        Returns:
            Extraction result containing requirements, decisions, and questions.
        """
        prompt = build_extraction_prompt(
            self.prompt_template,
            content=content,
            source=source,
            meeting_date=meeting_date,
            participants=participants,
            context=context,
        )

        logger.info(
            "extraction_started",
            content_length=len(content),
            source=source
        )

        try:
            # Call the LLM.
            response = await self._llm.complete(
                prompt=prompt,
                agent_id="requirement-manager",
                task_type="extraction",
                temperature=0,
                system_prompt=await self._system_prompt_resolver(
                    "requirement-manager",
                    _DEFAULT_SYSTEM_PROMPT,
                ),
            )

            # Parse the JSON response.
            result = self._parse_response(response)

            logger.info(
                "extraction_completed",
                requirements_count=len(result.requirements),
                decisions_count=len(result.decisions),
                questions_count=len(result.open_questions)
            )

            return result

        except Exception as e:
            logger.error("extraction_failed", error=str(e))
            raise

    def _parse_response(self, response: str) -> ExtractionResult:
        """Parse the LLM response."""
        try:
            parsed = LLMExtractionResponse.from_text(response)

            return ExtractionResult(
                requirements=[
                    ExtractedRequirement(
                        title=requirement.title,
                        description=requirement.description,
                        category=requirement.category,
                        priority=requirement.priority,
                        source_quote=requirement.source_quote,
                    )
                    for requirement in parsed.requirements
                ],
                decisions=[
                    ExtractedDecision(
                        content=decision.content,
                        decided_by=decision.decided_by,
                    )
                    for decision in parsed.decisions
                ],
                open_questions=[
                    ExtractedQuestion(
                        question=question.question,
                        context=question.context,
                    )
                    for question in parsed.open_questions
                ],
            )

        except ValueError as e:
            logger.error(
                "json_parse_failed",
                error=str(e),
                response_length=len(response or ""),
            )
            return ExtractionResult()
