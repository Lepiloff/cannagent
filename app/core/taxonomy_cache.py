"""
Taxonomy Cache - Cache taxonomy data with TTL and graceful degradation

Purpose:
- Cache taxonomy data in Redis with in-memory fallback
- Manage TTL (Time To Live)
- Graceful degradation on Redis failure
- Cache warming on startup
- Metrics for monitoring

Design Principles:
- Cache-Aside Pattern (standard, battle-tested)
- Dual caching: Redis (primary) + in-memory (fallback)
- Language-specific caching (EN/ES separate keys)
- Never returns None (always has data)
- Separation of Concerns (no business logic)

Performance:
- Redis cache hit: <5ms
- In-memory cache hit: <1ms
- DB load (cache miss): ~50-100ms
"""

import json
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    import redis

from app.db.taxonomy_repository import ITaxonomyRepository

logger = logging.getLogger(__name__)


class ITaxonomyCache(ABC):
    """Interface for taxonomy caching (Dependency Inversion Principle)"""

    @abstractmethod
    def get_taxonomy(self, language: str = "en") -> Dict[str, Any]:
        """
        Get cached taxonomy for given language

        Args:
            language: Language code ("en" or "es")

        Returns:
            {
                "flavors": ["tropical", "citrus", ...],
                "feelings": ["relaxed", "sleepy", ...],
                "helps_with": ["pain", "anxiety", ...],
                "negatives": ["dry mouth", "paranoia", ...],
                "terpenes": ["Myrcene", "Limonene", ...],
                "thc_range": {"min": 0.0, "max": 30.0},
                "cbd_range": {"min": 0.0, "max": 20.0},
                "categories": ["Indica", "Sativa", "Hybrid"],
                "stats": {
                    "total_flavors": 50,
                    "total_feelings": 20,
                    ...
                }
            }
        """
        pass

    @abstractmethod
    def invalidate_cache(self):
        """Invalidate cached taxonomy (e.g., after data sync)"""
        pass

    @abstractmethod
    def warm_cache(self):
        """Pre-load cache on startup"""
        pass


class TaxonomyCache(ITaxonomyCache):
    """
    Redis-backed taxonomy cache with graceful degradation

    Architecture:
    1. Try Redis cache (fast, shared across instances)
    2. Try in-memory cache (fallback, instance-local)
    3. Load from DB and cache (cache miss)

    Design Decisions:
    - Version in cache key (v1) for schema changes
    - 1-hour TTL (taxonomy changes rarely)
    - Language-specific caching (EN/ES)
    - Statistics for monitoring
    - Never returns None (always returns data)
    """

    # Cache keys with version
    CACHE_KEY_EN = "taxonomy:v1:en"
    CACHE_KEY_ES = "taxonomy:v1:es"

    # TTL: 1 hour (3600 seconds) - taxonomy doesn't change frequently
    CACHE_TTL = 3600

    def __init__(
        self,
        repository: ITaxonomyRepository,
        redis_client: Optional["redis.Redis"] = None
    ):
        """
        Args:
            repository: Taxonomy repository for data access
            redis_client: Redis client for caching (optional for graceful degradation)
        """
        self.repository = repository
        self.redis = redis_client
        self._in_memory_cache: Dict[str, Dict[str, Any]] = {}

        logger.info("TaxonomyCache initialized")

    def get_taxonomy(self, language: str = "en") -> Dict[str, Any]:
        """
        Get taxonomy with cache-aside pattern

        Flow:
        1. Try Redis cache (primary)
        2. Try in-memory cache (fallback)
        3. Load from DB and cache

        Args:
            language: Language code ("en" or "es")

        Returns:
            Taxonomy dict (never None, always returns data)
        """
        cache_key = self.CACHE_KEY_EN if language == "en" else self.CACHE_KEY_ES

        # Step 1: Try Redis cache
        if self.redis:
            try:
                cached_data = self.redis.get(cache_key)
                if cached_data:
                    logger.debug(f"Taxonomy cache HIT (Redis) for language={language}")
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Redis cache read failed: {e}")
                # Continue to fallback

        # Step 2: Try in-memory cache
        if cache_key in self._in_memory_cache:
            logger.debug(f"Taxonomy cache HIT (in-memory) for language={language}")
            return self._in_memory_cache[cache_key]

        # Step 3: Cache MISS - load from DB
        logger.info(f"Taxonomy cache MISS - loading from DB for language={language}")
        taxonomy = self._load_from_db(language)

        # Cache in Redis (best effort)
        if self.redis:
            try:
                self.redis.setex(
                    cache_key,
                    self.CACHE_TTL,
                    json.dumps(taxonomy)
                )
                logger.debug(f"Taxonomy cached in Redis (TTL={self.CACHE_TTL}s)")
            except Exception as e:
                logger.warning(f"Redis cache write failed: {e}")
                # Continue - in-memory cache still works

        # Always cache in-memory as fallback
        self._in_memory_cache[cache_key] = taxonomy
        logger.debug(f"Taxonomy cached in-memory")

        return taxonomy

    def _load_from_db(self, language: str) -> Dict[str, Any]:
        """
        Load taxonomy from database via repository

        Args:
            language: Language code ("en" or "es")

        Returns:
            Complete taxonomy dict with all characteristics
        """
        # Load bilingual data from repository
        flavors_raw = self.repository.get_all_flavors()
        feelings_raw = self.repository.get_all_feelings()
        helps_with_raw = self.repository.get_all_helps_with()
        negatives_raw = self.repository.get_all_negatives()
        terpenes = self.repository.get_all_terpenes()

        thc_range = self.repository.get_thc_range()
        cbd_range = self.repository.get_cbd_range()
        categories = self.repository.get_categories()

        # Extract language-specific names
        lang_field = "name_en" if language == "en" else "name_es"

        taxonomy = {
            # Characteristics (language-specific)
            "flavors": [f[lang_field] for f in flavors_raw if f.get(lang_field)],
            "feelings": [f[lang_field] for f in feelings_raw if f.get(lang_field)],
            "helps_with": [h[lang_field] for h in helps_with_raw if h.get(lang_field)],
            "negatives": [n[lang_field] for n in negatives_raw if n.get(lang_field)],
            "terpenes": terpenes,  # No translation (scientific names)

            # Ranges (from actual strain data)
            "thc_range": {"min": thc_range[0], "max": thc_range[1]},
            "cbd_range": {"min": cbd_range[0], "max": cbd_range[1]},

            # Categories (fixed)
            "categories": categories,

            # Statistics for logging/monitoring
            "stats": {
                "total_flavors": len(flavors_raw),
                "total_feelings": len(feelings_raw),
                "total_medical_uses": len(helps_with_raw),
                "total_negatives": len(negatives_raw),
                "total_terpenes": len(terpenes),
                "language": language
            }
        }

        logger.info(
            f"Loaded taxonomy from DB: "
            f"{taxonomy['stats']['total_flavors']} flavors, "
            f"{taxonomy['stats']['total_feelings']} feelings, "
            f"{taxonomy['stats']['total_medical_uses']} medical uses, "
            f"{taxonomy['stats']['total_terpenes']} terpenes"
        )

        return taxonomy

    def invalidate_cache(self):
        """
        Invalidate cache (e.g., after data sync)

        Usage:
            # In sync_strain_relations.py after sync completes:
            taxonomy_cache.invalidate_cache()

        This ensures fresh data after sync
        """
        logger.info("Invalidating taxonomy cache")

        # Clear Redis cache
        if self.redis:
            try:
                deleted_count = 0
                for key in [self.CACHE_KEY_EN, self.CACHE_KEY_ES]:
                    if self.redis.delete(key):
                        deleted_count += 1
                logger.info(f"Redis cache cleared: {deleted_count} keys deleted")
            except Exception as e:
                logger.warning(f"Redis cache invalidation failed: {e}")

        # Clear in-memory cache
        self._in_memory_cache.clear()
        logger.info("In-memory cache cleared")

    def warm_cache(self):
        """
        Warm cache on startup

        Pre-loads both EN and ES taxonomy to avoid cold start.
        Called during application initialization.
        """
        logger.info("Warming taxonomy cache...")

        try:
            # Load both languages
            en_taxonomy = self.get_taxonomy("en")
            es_taxonomy = self.get_taxonomy("es")

            logger.info(
                f"✅ Taxonomy cache warmed successfully: "
                f"EN ({en_taxonomy['stats']['total_flavors']} items), "
                f"ES ({es_taxonomy['stats']['total_flavors']} items)"
            )
        except Exception as e:
            logger.error(f"❌ Cache warming failed: {e}")
            # Not fatal - cache will load on first request


# Global cache instance (singleton pattern)
_taxonomy_cache_instance: Optional[TaxonomyCache] = None


def init_taxonomy_cache(
    repository: ITaxonomyRepository,
    redis_client: Optional["redis.Redis"] = None
) -> TaxonomyCache:
    """
    Initialize global taxonomy cache instance

    Args:
        repository: Taxonomy repository
        redis_client: Redis client (optional)

    Returns:
        TaxonomyCache instance
    """
    global _taxonomy_cache_instance

    _taxonomy_cache_instance = TaxonomyCache(repository, redis_client)
    logger.info("Global taxonomy cache initialized")

    return _taxonomy_cache_instance


def get_taxonomy_cache() -> TaxonomyCache:
    """
    Get global taxonomy cache instance

    Returns:
        TaxonomyCache instance

    Raises:
        RuntimeError: If cache not initialized
    """
    if _taxonomy_cache_instance is None:
        raise RuntimeError(
            "Taxonomy cache not initialized. "
            "Call init_taxonomy_cache() first."
        )

    return _taxonomy_cache_instance
