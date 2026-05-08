"""
Document generator.

Generates exported documents such as PRDs and open-question lists.
"""
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from shared.control_plane.agent_prompt_config import resolve_agent_system_prompt
from shared.infra.llm_gateway import llm_gateway
from shared.infra.prompt_boundaries import wrap_untrusted_json
from shared.utils.logger import get_logger

logger = get_logger("generator")

_DEFAULT_SYSTEM_PROMPT = (
    "You are a professional technical documentation expert specialized in "
    "product requirements documents."
)


class PRDGenerationResult(BaseModel):
    """PRD generation result."""
    content: str
    format: str = "markdown"
    generated_at: datetime
    requirements_count: int
    version: str


class QuestionExportResult(BaseModel):
    """Question-list export result."""
    content: str
    format: str = "markdown"
    generated_at: datetime
    questions_count: int


def build_prd_generation_prompt(
    prompt_template: str,
    *,
    requirements: list[dict],
    project_name: str,
    version: str,
    generated_date: str,
) -> str:
    """Build the PRD prompt with metadata and requirements isolated."""
    return prompt_template.format(
        project_metadata_block=wrap_untrusted_json(
            "untrusted_prd_metadata_json",
            {
                "project_name": project_name,
                "version": version,
                "generated_date": generated_date,
                "total_requirements": len(requirements),
            },
        ),
        requirements_block=wrap_untrusted_json(
            "untrusted_requirements_json",
            {"requirements": requirements},
        ),
    )


class DocumentGenerator:
    """
    Document generator.

    Supports:
    1. PRD generation through the LLM for professional formatting.
    2. Direct template-based open-question list generation without the LLM.
    """

    def __init__(self):
        # Load the PRD generation prompt.
        prompt_path = Path(__file__).parent.parent / "prompts" / "generate_prd.md"
        self.prd_prompt_template = prompt_path.read_text(encoding="utf-8")

    async def generate_prd(
        self,
        requirements: list[dict],
        project_name: str = "Wisdoverse Cell",
        version: str = "1.0"
    ) -> PRDGenerationResult:
        """
        Generate a PRD document.

        Args:
            requirements: Requirement list; each item contains:
                - id, title, description, category, priority, status, source_quote
            project_name: Project name.
            version: Document version.

        Returns:
            PRD generation result containing the generated Markdown document.
        """
        if not requirements:
            # Empty requirement list: return the empty template.
            return PRDGenerationResult(
                content=self._empty_prd_template(project_name, version),
                generated_at=datetime.now(UTC),
                requirements_count=0,
                version=version
            )

        generated_date = datetime.now(UTC).strftime("%Y-%m-%d")
        prompt = build_prd_generation_prompt(
            self.prd_prompt_template,
            requirements=requirements,
            project_name=project_name,
            version=version,
            generated_date=generated_date,
        )

        logger.info(
            "prd_generation_started",
            project_name=project_name,
            requirements_count=len(requirements)
        )

        try:
            # Call the LLM for generation.
            content = await llm_gateway.complete(
                prompt=prompt,
                agent_id="requirement-manager",
                task_type="document_generation",
                temperature=0.3,  # Slightly increase creativity.
                max_tokens=8192,  # PRDs may be long.
                system_prompt=await resolve_agent_system_prompt(
                    "requirement-manager",
                    _DEFAULT_SYSTEM_PROMPT,
                ),
            )

            # Clean possible Markdown code-fence wrappers.
            content = self._clean_markdown_response(content)

            logger.info(
                "prd_generation_completed",
                content_length=len(content)
            )

            return PRDGenerationResult(
                content=content,
                generated_at=datetime.now(UTC),
                requirements_count=len(requirements),
                version=version
            )

        except Exception as e:
            logger.error("prd_generation_failed", error=str(e))
            # Fallback: return a simple PRD.
            return PRDGenerationResult(
                content=self._fallback_prd(requirements, project_name, version),
                generated_at=datetime.now(UTC),
                requirements_count=len(requirements),
                version=version
            )

    def generate_questions_export(
        self,
        questions: list[dict],
        project_name: str = "Wisdoverse Cell"
    ) -> QuestionExportResult:
        """
        Generate an open-question list export.

        Does not use the LLM; generated directly from a template.

        Args:
            questions: Question list; each item contains:
                - id, question, context, status, requirement_title
            project_name: Project name.

        Returns:
            Question export result containing the Markdown question list.
        """
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")

        lines = [
            f"# {project_name} - 待确认问题清单",
            "",
            f"> 生成日期: {date_str}",
            f"> 总问题数: {len(questions)}",
            "",
            "---",
            "",
        ]

        if not questions:
            lines.extend([
                "## 暂无待确认问题",
                "",
                "所有问题已回答完毕。",
            ])
        else:
            # Group by status.
            open_questions = [q for q in questions if q.get("status") == "open"]
            answered_questions = [q for q in questions if q.get("status") == "answered"]

            if open_questions:
                lines.extend([
                    f"## 待回答问题 ({len(open_questions)})",
                    "",
                ])

                for i, q in enumerate(open_questions, 1):
                    lines.extend([
                        f"### {i}. {q.get('question', '未知问题')}",
                        "",
                    ])
                    if q.get("context"):
                        lines.append(f"**背景**: {q['context']}")
                        lines.append("")
                    if q.get("requirement_title"):
                        lines.append(f"**关联需求**: {q['requirement_title']}")
                        lines.append("")
                    lines.append(f"**问题ID**: `{q.get('id', 'N/A')}`")
                    lines.append("")
                    lines.append("**回答**: _______________________")
                    lines.append("")
                    lines.append("---")
                    lines.append("")

            if answered_questions:
                lines.extend([
                    f"## 已回答问题 ({len(answered_questions)})",
                    "",
                ])

                for q in answered_questions:
                    lines.extend([
                        f"- **{q.get('question', '未知问题')}**",
                        f"  - 回答: {q.get('answer', '无')}",
                        f"  - 回答人: {q.get('answered_by', '未知')}",
                        "",
                    ])

        lines.extend([
            "---",
            "",
            f"*本文档由 {project_name} 需求管理系统自动生成*",
        ])

        content = "\n".join(lines)

        logger.info(
            "questions_export_generated",
            total_questions=len(questions),
            open_count=len([q for q in questions if q.get("status") == "open"])
        )

        return QuestionExportResult(
            content=content,
            generated_at=now,
            questions_count=len(questions)
        )

    def _clean_markdown_response(self, content: str) -> str:
        """Clean possible code-fence wrappers from an LLM response."""
        content = content.strip()
        if content.startswith("```markdown"):
            content = content[11:]
        if content.startswith("```md"):
            content = content[5:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def _empty_prd_template(self, project_name: str, version: str) -> str:
        """Return a PRD template for an empty requirement list."""
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        return f"""# {project_name} - 产品需求文档

> 版本: {version}
> 生成日期: {date_str}
> 状态: 自动生成

---

## 文档概述

本文档暂无需求数据。请先通过会议记录导入功能添加需求。

---

*本文档由 {project_name} 需求管理系统自动生成*
"""

    def _fallback_prd(
        self,
        requirements: list[dict],
        project_name: str,
        version: str
    ) -> str:
        """Generate a fallback PRD when the LLM call fails."""
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")

        lines = [
            f"# {project_name} - 产品需求文档",
            "",
            f"> 版本: {version}",
            f"> 生成日期: {date_str}",
            "> 状态: 自动生成 (简化版)",
            "",
            "---",
            "",
            "## 需求列表",
            "",
            "| 编号 | 标题 | 分类 | 优先级 | 状态 |",
            "|------|------|------|--------|------|",
        ]

        # Sort by category.
        sorted_reqs = sorted(
            requirements,
            key=lambda x: (
                x.get("category", ""),
                x.get("priority", ""),
            ),
        )

        for i, req in enumerate(sorted_reqs, 1):
            lines.append(
                f"| REQ-{i:03d} | {req.get('title', '未知')} | "
                f"{req.get('category', '其他')} | {req.get('priority', '中')} | "
                f"{req.get('status', '待确认')} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 需求详情",
            "",
        ])

        for i, req in enumerate(sorted_reqs, 1):
            lines.extend([
                f"### REQ-{i:03d}: {req.get('title', '未知')}",
                "",
                f"- **分类**: {req.get('category', '其他')}",
                f"- **优先级**: {req.get('priority', '中')}",
                f"- **状态**: {req.get('status', '待确认')}",
                "",
                f"**描述**: {req.get('description', '无描述')}",
                "",
            ])
            if req.get("source_quote"):
                lines.append(f"> 原文: {req['source_quote']}")
                lines.append("")
            lines.append("---")
            lines.append("")

        lines.extend([
            f"*本文档由 {project_name} 需求管理系统自动生成*",
        ])

        return "\n".join(lines)


# Global generator instance.
generator = DocumentGenerator()
