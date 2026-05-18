"""Requirement text formatting helpers for vector indexing."""

from typing import Optional

from pydantic import BaseModel


class EmbeddingResult(BaseModel):
    """Embedding result."""

    text: str
    embedding: list[float]
    model: str


class RequirementEmbedder:
    """Requirement vector-text formatter.

    Actual embedding is an infrastructure concern owned by the vector-store
    adapter. This core helper only defines the domain-specific text shape used
    before indexing and semantic search.
    """

    def format_requirement_for_embedding(
        self,
        title: str,
        description: str,
        category: Optional[str] = None,
    ) -> str:
        """Format requirement text for higher-quality embeddings."""
        parts = [f"需求: {title}"]
        if category:
            parts.append(f"分类: {category}")
        parts.append(f"描述: {description}")
        return "\n".join(parts)
