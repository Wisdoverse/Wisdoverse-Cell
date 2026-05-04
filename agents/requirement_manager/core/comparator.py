"""
Requirement relationship comparator.

Uses vector similarity and LLM analysis to detect relationships between
requirements:
- Duplicate requirements
- Updates or refinements
- Conflicts
"""
import json
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from shared.infra.llm_gateway import llm_gateway
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("comparator")


def _get_vector_store():
    """Import lazily to avoid circular dependencies."""
    from ..db.vector_store import vector_store
    return vector_store


class RelationType(str, Enum):
    """Requirement relationship type."""
    NEW = "new"              # New requirement
    DUPLICATE = "duplicate"  # Duplicate requirement
    UPDATE = "update"        # Update or refinement
    CONFLICT = "conflict"    # Conflict


class ComparisonResult(BaseModel):
    """Comparison result."""
    relation: RelationType
    confidence: float = Field(ge=0, le=1, description="Decision confidence")
    explanation: str
    suggested_action: str
    related_requirement_id: Optional[str] = None
    merge_suggestion: Optional[str] = None


class RequirementComparator:
    """
    Requirement comparator.

    Workflow:
    1. Use vector search to find similar requirements.
    2. If no similar requirement is found, classify the requirement as new.
    3. If similar requirements exist, call the LLM for deeper relationship analysis.

    This two-stage approach balances speed and accuracy:
    - Most new requirements skip LLM calls quickly.
    - Only potential conflicts or duplicates need deeper analysis.
    """

    def __init__(self):
        # Load the prompt template.
        prompt_path = Path(__file__).parent.parent / "prompts" / "detect_conflicts.md"
        self.prompt_template = prompt_path.read_text(encoding="utf-8")

        # Similarity thresholds.
        self.similarity_threshold = 0.6  # Values below this are considered unrelated.
        self.duplicate_threshold = 0.85  # Values above this may be duplicates.

    async def compare(
        self,
        new_title: str,
        new_description: str,
        new_category: Optional[str] = None,
        exclude_ids: Optional[list[str]] = None
    ) -> ComparisonResult:
        """
        Compare a new requirement with existing requirements.

        Args:
            new_title: New requirement title.
            new_description: New requirement description.
            new_category: New requirement category.
            exclude_ids: Requirement IDs to exclude, such as the one being edited.

        Returns:
            Comparison result.
        """
        # Build search text.
        search_text = f"{new_title} {new_description}"

        # Vector-search similar requirements.
        similar = await _get_vector_store().search(
            query=search_text,
            n_results=5,
            min_similarity=self.similarity_threshold
        )

        # Exclude specified IDs.
        if exclude_ids:
            similar = [s for s in similar if s["id"] not in exclude_ids]

        # No similar requirements means this is a new requirement.
        if not similar:
            logger.info(
                "no_similar_requirements",
                title_hash=hash_identifier(new_title),
                title_length=len(new_title),
            )
            return ComparisonResult(
                relation=RelationType.NEW,
                confidence=0.95,
                explanation="未找到语义相似的已有需求",
                suggested_action="直接创建新需求"
            )

        # Check for high similarity, which may indicate a duplicate.
        top_similar = similar[0]
        if top_similar["similarity"] >= self.duplicate_threshold:
            # High similarity can return quickly as a likely duplicate.
            logger.info(
                "high_similarity_detected",
                title_hash=hash_identifier(new_title),
                title_length=len(new_title),
                similar_id=top_similar["id"],
                similarity=top_similar["similarity"],
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

        # Medium similarity needs deeper LLM analysis.
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
        """Use the LLM for deeper requirement relationship analysis."""
        # Format similar requirements.
        similar_text = "\n".join([
            f"- ID: {s['id']}\n  Title: {s['title']}\n"
            f"  Category: {s['category']}\n"
            f"  Similarity: {s['similarity']:.2%}"
            for s in similar_requirements
        ])

        # Build the prompt.
        prompt = self.prompt_template.format(
            new_title=new_title,
            new_description=new_description,
            new_category=new_category or "uncategorized",
            similar_requirements=similar_text
        )

        logger.info(
            "llm_conflict_analysis_started",
            title_hash=hash_identifier(new_title),
            title_length=len(new_title),
            similar_count=len(similar_requirements),
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
                title_hash=hash_identifier(new_title),
                title_length=len(new_title),
                relation=result.relation.value,
                confidence=result.confidence,
            )

            return result

        except Exception as e:
            logger.error("llm_conflict_analysis_failed", error=str(e))
            # Fallback: return a result that requires human review.
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
        """Parse the LLM response."""
        try:
            # Clean the response.
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Map relationship types.
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
            # Default response when parsing fails.
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
        Check a batch of requirements for conflicts.

        Args:
            requirements: Requirement list; each item contains title, description, and category.

        Returns:
            A list of (requirement, comparison result) tuples.
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


# Global comparator instance.
comparator = RequirementComparator()
