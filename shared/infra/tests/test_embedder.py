"""Tests for the shared TextEmbedder."""

from unittest.mock import MagicMock, patch

import pytest

from shared.infra.embedder import TextEmbedder


class TestTextEmbedderConstruction:
    def test_default_model_name(self):
        e = TextEmbedder()
        assert e._model_name == "all-MiniLM-L6-v2"

    def test_custom_model_name(self):
        e = TextEmbedder(model_name="custom-model")
        assert e._model_name == "custom-model"

    def test_model_not_loaded_until_needed(self):
        e = TextEmbedder()
        assert e._model is None


class TestTextEmbedderEmbed:
    def test_embed_returns_list_of_floats(self):
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])

        e = TextEmbedder()
        e._model = mock_model

        result = e.embed("hello")
        assert result == [0.1, 0.2, 0.3]
        mock_model.encode.assert_called_once_with("hello")

    def test_embed_raises_on_empty_text(self):
        e = TextEmbedder()
        with pytest.raises(ValueError, match="empty"):
            e.embed("")

    def test_embed_raises_on_whitespace_only(self):
        e = TextEmbedder()
        with pytest.raises(ValueError, match="empty"):
            e.embed("   ")


class TestTextEmbedderEmbedBatch:
    def test_embed_batch_returns_list(self):
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])

        e = TextEmbedder()
        e._model = mock_model

        result = e.embed_batch(["hello", "world"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_batch_empty_list(self):
        e = TextEmbedder()
        assert e.embed_batch([]) == []

    def test_embed_batch_raises_on_empty_strings(self):
        e = TextEmbedder()
        with pytest.raises(ValueError, match=r"indices \[1, 2\]"):
            e.embed_batch(["hello", "", "  "])

    def test_embed_batch_all_empty_raises(self):
        e = TextEmbedder()
        with pytest.raises(ValueError, match="Empty or whitespace-only"):
            e.embed_batch(["", "  "])


class TestTextEmbedderLazyLoading:
    def test_load_initializes_model(self):
        mock_st = MagicMock()
        mock_instance = MagicMock()
        mock_st.return_value = mock_instance

        with patch("shared.infra.embedder.SentenceTransformer", mock_st, create=True):
            # Need to patch at the point of import inside _load
            with patch.dict(
                "sys.modules",
                {"sentence_transformers": MagicMock(SentenceTransformer=mock_st)},
            ):
                e = TextEmbedder()
                e._load()
                assert e._model is mock_instance


class TestTextEmbedderDimension:
    def test_dimension_property(self):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384

        e = TextEmbedder()
        e._model = mock_model

        assert e.dimension == 384
