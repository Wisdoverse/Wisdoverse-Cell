"""Text embedding using sentence-transformers (local, no API calls).

Default model: ``all-MiniLM-L6-v2`` (384 dimensions).
"""

from __future__ import annotations

import threading

from shared.utils.logger import get_logger

logger = get_logger("infra.embedder")

DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_DIMENSION = 384


class TextEmbedder:
    """Lazy-loading text embedder backed by sentence-transformers."""

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or DEFAULT_MODEL
        self._model = None
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self._model_name)
                    logger.info("embedder_loaded", model=self._model_name)

    @property
    def dimension(self) -> int:
        """Embedding vector dimension for the loaded model."""
        self._load()
        return self._model.get_sentence_embedding_dimension()  # type: ignore[union-attr]

    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        if not text or not text.strip():
            raise ValueError("Text must not be empty")
        self._load()
        return self._model.encode(text).tolist()  # type: ignore[union-attr]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one call.

        Raises ``ValueError`` if any text is empty or whitespace-only.
        All inputs must be non-empty to guarantee 1:1 correspondence
        between inputs and returned embeddings.
        """
        if not texts:
            return []
        invalid = [i for i, t in enumerate(texts) if not t or not t.strip()]
        if invalid:
            raise ValueError(f"Empty or whitespace-only texts at indices {invalid}")
        self._load()
        return self._model.encode(texts).tolist()  # type: ignore[union-attr]


# Global singleton — import and use directly.
embedder = TextEmbedder()
