"""Requirement embedding helpers.

Uses the shared TextEmbedder (sentence-transformers, all-MiniLM-L6-v2).
"""

from typing import Optional

from pydantic import BaseModel

from shared.infra.embedder import embedder as _shared_embedder
from shared.utils.logger import get_logger

logger = get_logger("embedder")


class EmbeddingResult(BaseModel):
    """Embedding result."""

    text: str
    embedding: list[float]
    model: str


class RequirementEmbedder:
    """Requirement embedder.

    Converts requirement text into vectors for:
    1. Semantic search by natural-language query.
    2. Similarity checks for duplicate or related requirements.
    3. Conflict checks for potentially contradictory requirements.

    Backed by ``shared.infra.embedder.TextEmbedder`` (all-MiniLM-L6-v2, 384 dim).
    """

    def embed_text(self, text: str) -> list[float]:
        """Convert text to a 384-dimensional embedding."""
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        return _shared_embedder.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        if not texts:
            return []
        return _shared_embedder.embed_batch(texts)

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


# Global embedder instance.
embedder = RequirementEmbedder()
