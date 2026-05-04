"""
Requirement extraction core logic.

Extracts structured requirements from meeting records through the LLM Gateway.
"""
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from shared.infra.llm_gateway import llm_gateway
from shared.infra.prompt_boundaries import wrap_untrusted_json
from shared.utils.logger import get_logger

logger = get_logger("extractor")


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

    def __init__(self):
        # Load the prompt template.
        prompt_path = Path(__file__).parent.parent / "prompts" / "extract_requirements.md"
        self.prompt_template = prompt_path.read_text(encoding="utf-8")

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
            response = await llm_gateway.complete(
                prompt=prompt,
                agent_id="requirement-manager",
                task_type="extraction",
                temperature=0,
                system_prompt=(
                    "You are a professional product requirements analyst. "
                    "You are skilled at extracting structured requirements "
                    "from meeting notes."
                )
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
        # Try to extract JSON from the response.
        try:
            # Clean responses that may contain Markdown code fences.
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Parse requirements.
            requirements = []
            for req in data.get("requirements", []):
                requirements.append(ExtractedRequirement(
                    title=req.get("title", ""),
                    description=req.get("description", ""),
                    category=self._normalize_category(req.get("category", "功能")),
                    priority=self._normalize_priority(req.get("priority", "medium")),
                    source_quote=req.get("source_quote")
                ))

            # Parse decisions.
            decisions = []
            for dec in data.get("decisions", []):
                decisions.append(ExtractedDecision(
                    content=dec.get("content", ""),
                    decided_by=dec.get("decided_by")
                ))

            # Parse questions.
            questions = []
            for q in data.get("open_questions", []):
                questions.append(ExtractedQuestion(
                    question=q.get("question", ""),
                    context=q.get("context")
                ))

            return ExtractionResult(
                requirements=requirements,
                decisions=decisions,
                open_questions=questions
            )

        except json.JSONDecodeError as e:
            logger.error(
                "json_parse_failed",
                error=str(e),
                response_length=len(response or ""),
            )
            return ExtractionResult()

    def _normalize_category(self, category: str) -> str:
        """Normalize category names."""
        normalized = category.lower()
        category_map = {
            "功能": "功能",
            "feature": "功能",
            "性能": "性能",
            "performance": "性能",
            "硬件": "硬件",
            "hardware": "硬件",
            "集成": "集成",
            "integration": "集成",
            "ui": "UI",
            "UI": "UI",
            "用户界面": "UI",
            "安全": "安全",
            "security": "安全",
        }
        return category_map.get(category, category_map.get(normalized, "其他"))

    def _normalize_priority(self, priority: str) -> str:
        """Normalize priority values."""
        priority_map = {
            "high": "high",
            "高": "high",
            "medium": "medium",
            "中": "medium",
            "low": "low",
            "低": "low",
        }
        return priority_map.get(priority.lower(), "medium")


# Global extractor instance.
extractor = RequirementExtractor()
