"""Embedder - 需求向量化

Uses the shared TextEmbedder (sentence-transformers, all-MiniLM-L6-v2).
"""

from typing import Optional

from pydantic import BaseModel

from shared.infra.embedder import embedder as _shared_embedder
from shared.utils.logger import get_logger

logger = get_logger("embedder")


class EmbeddingResult(BaseModel):
    """嵌入结果"""

    text: str
    embedding: list[float]
    model: str


class RequirementEmbedder:
    """需求向量化器

    将需求文本转换为向量，用于:
    1. 语义搜索 - 根据自然语言查找相关需求
    2. 相似度检测 - 找出重复或相关的需求
    3. 冲突检测 - 识别可能矛盾的需求

    Backed by ``shared.infra.embedder.TextEmbedder`` (all-MiniLM-L6-v2, 384 dim).
    """

    def embed_text(self, text: str) -> list[float]:
        """将文本转换为向量 (384维)"""
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        return _shared_embedder.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本"""
        if not texts:
            return []
        return _shared_embedder.embed_batch(texts)

    def format_requirement_for_embedding(
        self,
        title: str,
        description: str,
        category: Optional[str] = None,
    ) -> str:
        """格式化需求文本以获得更好的嵌入效果"""
        parts = [f"需求: {title}"]
        if category:
            parts.append(f"分类: {category}")
        parts.append(f"描述: {description}")
        return "\n".join(parts)


# 全局嵌入器实例
embedder = RequirementEmbedder()
