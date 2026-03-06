"""
Cached Embedding Provider — transparent caching decorator for any EmbeddingProvider.

Wraps an EmbeddingProvider and caches results in Redis via CacheService.
Eliminates duplicate inline cache logic from SmartRAGService.
"""

import logging
from typing import List

from app.core.llm_interface import EmbeddingProvider

logger = logging.getLogger(__name__)


class CachedEmbeddingProvider(EmbeddingProvider):
    """Transparent caching decorator for any EmbeddingProvider."""

    def __init__(self, provider: EmbeddingProvider, cache_service):
        self._provider = provider
        self._cache = cache_service

    def generate_embedding(self, text: str) -> List[float]:
        # Sync path has no cache (cache is async-only via aiocache)
        return self._provider.generate_embedding(text)

    async def agenerate_embedding(self, text: str) -> List[float]:
        # Try cache first
        try:
            cached = await self._cache.get_embedding(text)
            if cached is not None:
                logger.debug("Embedding cache hit")
                return cached
        except Exception as e:
            logger.warning(f"Embedding cache read failed: {e}")

        # Generate and cache
        embedding = await self._provider.agenerate_embedding(text)
        if embedding:
            try:
                await self._cache.set_embedding(text, embedding)
            except Exception as e:
                logger.warning(f"Embedding cache write failed: {e}")

        return embedding
