"""Local embedding via sentence-transformers.

Model and dimension from shared.config (EMBEDDING_MODEL, EMBEDDING_DIMENSION).
Default: sentence-transformers/all-MiniLM-L6-v2, 384 dims.
"""
import logging
import os
from typing import List, Union

from shared.cache import clear_cache, get_cache_value, set_cache_value

logger = logging.getLogger(__name__)

_ENCODER_CACHE_KEY = "ingestion_embedding_encoder"


def get_encoder(model_name: str | None = None):
    """Return a lazy-loaded SentenceTransformer encoder."""
    if model_name is None:
        from shared.config import EMBEDDING_MODEL
        model_name = EMBEDDING_MODEL
    cached = get_cache_value(_ENCODER_CACHE_KEY, lambda: None)
    if cached is not None:
        return cached
    try:
        from sentence_transformers import SentenceTransformer
        encoder = SentenceTransformer(model_name)
        logger.info("Loaded embedding model: %s", model_name)
        return set_cache_value(_ENCODER_CACHE_KEY, encoder)
    except ImportError as e:
        raise ImportError(
            "sentence-transformers required for embeddings. "
            "Install with: pip install sentence-transformers"
        ) from e


def encode(texts: Union[str, List[str]], model_name: str | None = None) -> List[List[float]]:
    """Encode text(s) to vectors using config EMBEDDING_MODEL.

    Args:
        texts: Single string or list of strings.
        model_name: Model to use (default: from config).

    Returns:
        List of vectors. Dimension matches EMBEDDING_DIMENSION from config.
    """
    if isinstance(texts, str):
        texts = [texts]
    if os.environ.get("STORYTELLER_DUMMY_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes"):
        from shared.config import EMBEDDING_DIMENSION
        return [[0.0] * EMBEDDING_DIMENSION for _ in texts]
    enc = get_encoder(model_name)
    vectors = enc.encode(texts, show_progress_bar=False)
    return vectors.tolist()


def clear_embedding_cache() -> None:
    """Clear cached embedding model (useful for tests)."""
    clear_cache(_ENCODER_CACHE_KEY)
