"""
Comparator - 需求冲突检测

使用向量相似度和LLM分析检测需求之间的关系：
- 重复需求
- 更新/细化
- 冲突矛盾
"""
import json
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from shared.infra.llm_gateway import llm_gateway
from shared.utils.logger import get_logger

logger = get_logger("comparator")


def _get_vector_store():
    """延迟导入以避免循环依赖"""
    from ..db.vector_store import vector_store
    return vector_store


class RelationType(str, Enum):
    """需求关系类型"""
    NEW = "new"              # 全新需求
    DUPLICATE = "duplicate"  # 重复需求
    UPDATE = "update"        # 更新/细化
    CONFLICT = "conflict"    # 冲突矛盾


class ComparisonResult(BaseModel):
    """比对结果"""
    relation: RelationType
    confidence: float = Field(ge=0, le=1, description="Decision confidence")
    explanation: str
    suggested_action: str
    related_requirement_id: Optional[str] = None
    merge_suggestion: Optional[str] = None


class RequirementComparator:
    """
    需求比对器

    工作流程:
    1. 使用向量搜索找到相似需求
    2. 如果没有相似需求 -> 直接判定为 new
    3. 如果有相似需求 -> 调用 LLM 深度分析关系

    这种两阶段方法平衡了速度和准确度:
    - 大多数新需求可以快速跳过 LLM 调用
    - 只有潜在冲突/重复的需求才需要深度分析
    """

    def __init__(self):
        # 加载 prompt 模板
        prompt_path = Path(__file__).parent.parent / "prompts" / "detect_conflicts.md"
        self.prompt_template = prompt_path.read_text(encoding="utf-8")

        # 相似度阈值
        self.similarity_threshold = 0.6  # 低于此值认为无关
        self.duplicate_threshold = 0.85  # 高于此值可能是重复

    async def compare(
        self,
        new_title: str,
        new_description: str,
        new_category: Optional[str] = None,
        exclude_ids: Optional[list[str]] = None
    ) -> ComparisonResult:
        """
        比对新需求与已有需求

        Args:
            new_title: 新需求标题
            new_description: 新需求描述
            new_category: 新需求分类
            exclude_ids: 排除的需求ID列表（如正在编辑的需求本身）

        Returns:
            ComparisonResult 比对结果
        """
        # 构建搜索文本
        search_text = f"{new_title} {new_description}"

        # 向量搜索相似需求
        similar = await _get_vector_store().search(
            query=search_text,
            n_results=5,
            min_similarity=self.similarity_threshold
        )

        # 排除指定ID
        if exclude_ids:
            similar = [s for s in similar if s["id"] not in exclude_ids]

        # 没有相似需求 -> 新需求
        if not similar:
            logger.info(
                "no_similar_requirements",
                title=new_title
            )
            return ComparisonResult(
                relation=RelationType.NEW,
                confidence=0.95,
                explanation="未找到语义相似的已有需求",
                suggested_action="直接创建新需求"
            )

        # 检查是否有高度相似的（可能重复）
        top_similar = similar[0]
        if top_similar["similarity"] >= self.duplicate_threshold:
            # 高度相似，可能是重复，快速返回
            logger.info(
                "high_similarity_detected",
                title=new_title,
                similar_id=top_similar["id"],
                similarity=top_similar["similarity"]
            )
            return ComparisonResult(
                relation=RelationType.DUPLICATE,
                confidence=top_similar["similarity"],
                explanation=(
                    f"与已有需求「{top_similar['title']}」高度相似"
                    f" (相似度: {top_similar['similarity']:.2%})"
                ),
                suggested_action="建议检查是否为重复需求，考虑合并",
                related_requirement_id=top_similar["id"]
            )

        # 中等相似度，需要 LLM 深度分析
        return await self._llm_analyze(
            new_title=new_title,
            new_description=new_description,
            new_category=new_category,
            similar_requirements=similar
        )

    async def _llm_analyze(
        self,
        new_title: str,
        new_description: str,
        new_category: Optional[str],
        similar_requirements: list[dict]
    ) -> ComparisonResult:
        """使用 LLM 深度分析需求关系"""
        # 格式化相似需求
        similar_text = "\n".join([
            f"- ID: {s['id']}\n  Title: {s['title']}\n"
            f"  Category: {s['category']}\n"
            f"  Similarity: {s['similarity']:.2%}"
            for s in similar_requirements
        ])

        # 构建 prompt
        prompt = self.prompt_template.format(
            new_title=new_title,
            new_description=new_description,
            new_category=new_category or "uncategorized",
            similar_requirements=similar_text
        )

        logger.info(
            "llm_conflict_analysis_started",
            title=new_title,
            similar_count=len(similar_requirements)
        )

        try:
            response = await llm_gateway.complete(
                prompt=prompt,
                agent_id="requirement-manager",
                task_type="conflict_detection",
                temperature=0,
            system_prompt=(
                "You are a professional requirements analysis expert. "
                "You are skilled at identifying relationships between requirements."
            )
            )

            result = self._parse_response(response, similar_requirements)

            logger.info(
                "llm_conflict_analysis_completed",
                title=new_title,
                relation=result.relation.value,
                confidence=result.confidence
            )

            return result

        except Exception as e:
            logger.error("llm_conflict_analysis_failed", error=str(e))
            # 降级处理：返回需要人工审核
            return ComparisonResult(
                relation=RelationType.NEW,
                confidence=0.5,
                explanation=(
                    "自动分析失败，建议人工审核。"
                    f"相似需求: {similar_requirements[0]['title']}"
                ),
                suggested_action=(
                    "请人工检查是否与已有需求重复或冲突"
                ),
                related_requirement_id=(
                    similar_requirements[0]["id"]
                    if similar_requirements else None
                )
            )

    def _parse_response(
        self,
        response: str,
        similar_requirements: list[dict]
    ) -> ComparisonResult:
        """解析 LLM 响应"""
        try:
            # 清理响应
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # 映射关系类型
            relation_map = {
                "new": RelationType.NEW,
                "duplicate": RelationType.DUPLICATE,
                "update": RelationType.UPDATE,
                "conflict": RelationType.CONFLICT
            }

            relation = relation_map.get(
                data.get("relation", "new").lower(),
                RelationType.NEW
            )

            return ComparisonResult(
                relation=relation,
                confidence=float(data.get("confidence", 0.7)),
                explanation=data.get("explanation", ""),
                suggested_action=data.get("suggested_action", ""),
                related_requirement_id=data.get("related_requirement_id"),
                merge_suggestion=data.get("merge_suggestion")
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("parse_conflict_response_failed", error=str(e))
            # 解析失败时的默认响应
            return ComparisonResult(
                relation=RelationType.NEW,
                confidence=0.5,
                explanation="响应解析失败，建议人工审核",
                suggested_action="请人工检查需求关系",
                related_requirement_id=(
                    similar_requirements[0]["id"]
                    if similar_requirements else None
                )
            )

    async def check_batch(
        self,
        requirements: list[dict]
    ) -> list[tuple[dict, ComparisonResult]]:
        """
        批量检查需求冲突

        Args:
            requirements: 需求列表，每个包含 title, description, category

        Returns:
            (需求, 比对结果) 元组列表
        """
        results = []
        for req in requirements:
            result = await self.compare(
                new_title=req["title"],
                new_description=req["description"],
                new_category=req.get("category")
            )
            results.append((req, result))

        return results


# 全局比对器实例
comparator = RequirementComparator()
