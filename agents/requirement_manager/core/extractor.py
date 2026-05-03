"""
Requirement Extractor - 需求提取核心逻辑

从会议记录中使用LLM提取结构化需求。
"""
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from shared.infra.llm_gateway import llm_gateway
from shared.utils.logger import get_logger

logger = get_logger("extractor")


class ExtractedRequirement(BaseModel):
    """提取的需求结构"""
    title: str
    description: str
    category: str = "功能"
    priority: str = "medium"
    source_quote: Optional[str] = None


class ExtractedDecision(BaseModel):
    """提取的决定"""
    content: str
    decided_by: Optional[str] = None


class ExtractedQuestion(BaseModel):
    """提取的待确认问题"""
    question: str
    context: Optional[str] = None


class ExtractionResult(BaseModel):
    """提取结果"""
    requirements: list[ExtractedRequirement] = []
    decisions: list[ExtractedDecision] = []
    open_questions: list[ExtractedQuestion] = []


class RequirementExtractor:
    """
    需求提取器

    使用LLM从会议记录中提取:
    - 结构化需求
    - 做出的决定
    - 待确认的问题
    """

    def __init__(self):
        # 加载prompt模板
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
        从会议内容中提取需求

        Args:
            content: 会议内容文本
            source: 来源 (feishu/upload/wechat)
            meeting_date: 会议日期
            participants: 参与者列表
            context: 额外上下文说明

        Returns:
            ExtractionResult 包含需求、决定和问题
        """
        # 构建prompt
        prompt = self.prompt_template.format(
            meeting_content=content,
            source=source,
            meeting_date=meeting_date or "未知",
            participants=", ".join(participants) if participants else "未知",
            context=context or "无"
        )

        logger.info(
            "extraction_started",
            content_length=len(content),
            source=source
        )

        try:
            # 调用LLM
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

            # 解析JSON响应
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
        """解析LLM响应"""
        # 尝试从响应中提取JSON
        try:
            # 清理响应（可能包含markdown代码块）
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # 解析需求
            requirements = []
            for req in data.get("requirements", []):
                requirements.append(ExtractedRequirement(
                    title=req.get("title", ""),
                    description=req.get("description", ""),
                    category=self._normalize_category(req.get("category", "功能")),
                    priority=self._normalize_priority(req.get("priority", "medium")),
                    source_quote=req.get("source_quote")
                ))

            # 解析决定
            decisions = []
            for dec in data.get("decisions", []):
                decisions.append(ExtractedDecision(
                    content=dec.get("content", ""),
                    decided_by=dec.get("decided_by")
                ))

            # 解析问题
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
            logger.error("json_parse_failed", error=str(e), response=response[:500])
            return ExtractionResult()

    def _normalize_category(self, category: str) -> str:
        """规范化分类名称"""
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
        """规范化优先级"""
        priority_map = {
            "high": "high",
            "高": "high",
            "medium": "medium",
            "中": "medium",
            "low": "low",
            "低": "low",
        }
        return priority_map.get(priority.lower(), "medium")


# 全局提取器实例
extractor = RequirementExtractor()
