"""
Taxonomy Initialization Module

Purpose:
- Initialize all taxonomy-related components
- Handle dependency injection
- Manage feature flags
- Warm cache on startup

Usage:
    from app.core.taxonomy_init import initialize_taxonomy_system

    # In main.py or app startup:
    initialize_taxonomy_system(db_session, redis_client)
"""

import os
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.db.taxonomy_repository import TaxonomyRepository, ITaxonomyRepository
from app.core.taxonomy_cache import TaxonomyCache, init_taxonomy_cache, get_taxonomy_cache
from app.core.context_builder import ContextBuilder, create_context_builder
from app.core.fuzzy_matcher import create_composite_matcher, CompositeMatcher

logger = logging.getLogger(__name__)


class TaxonomySystem:
    """
    Container for all taxonomy-related components

    Design:
    - Dependency Injection Container
    - Lazy initialization
    - Feature flag support
    """

    def __init__(
        self,
        repository: ITaxonomyRepository,
        cache: TaxonomyCache,
        context_builder: ContextBuilder,
        fuzzy_matcher: CompositeMatcher
    ):
        self.repository = repository
        self.cache = cache
        self.context_builder = context_builder
        self.fuzzy_matcher = fuzzy_matcher

        logger.info("TaxonomySystem initialized")

    def warm_cache(self):
        """Warm cache on startup"""
        logger.info("Warming taxonomy cache...")
        self.cache.warm_cache()

    def invalidate_cache(self):
        """Invalidate cache (after data sync)"""
        logger.info("Invalidating taxonomy cache...")
        self.cache.invalidate_cache()


# Global instance (singleton)
_taxonomy_system: Optional[TaxonomySystem] = None


def initialize_taxonomy_system(
    db_session: Session,
    redis_client: Optional[object] = None,
    warm_cache: bool = True
) -> TaxonomySystem:
    """
    Initialize taxonomy system with all components

    Args:
        db_session: SQLAlchemy database session
        redis_client: Redis client (optional for graceful degradation)
        warm_cache: Whether to warm cache on startup

    Returns:
        TaxonomySystem instance
    """
    global _taxonomy_system

    logger.info("🚀 Initializing DB-Aware Taxonomy System...")

    # Initialize repository
    repository = TaxonomyRepository(db_session)
    logger.info("✅ TaxonomyRepository initialized")

    # Initialize cache
    cache = init_taxonomy_cache(repository, redis_client)
    logger.info("✅ TaxonomyCache initialized")

    # Initialize context builder
    context_builder = create_context_builder(cache)
    logger.info("✅ ContextBuilder initialized")

    # Initialize fuzzy matcher
    fuzzy_matcher = create_composite_matcher(db_session)
    logger.info("✅ FuzzyMatcher initialized")

    # Create system container
    _taxonomy_system = TaxonomySystem(
        repository=repository,
        cache=cache,
        context_builder=context_builder,
        fuzzy_matcher=fuzzy_matcher
    )

    # Warm cache if requested
    if warm_cache:
        try:
            _taxonomy_system.warm_cache()
            logger.info("✅ Cache warmed successfully")
        except Exception as e:
            logger.warning(f"Cache warming failed (non-fatal): {e}")

    logger.info("🎉 DB-Aware Taxonomy System initialized successfully!")
    return _taxonomy_system


def get_taxonomy_system() -> Optional[TaxonomySystem]:
    """
    Get global taxonomy system instance

    Returns:
        TaxonomySystem instance or None if not initialized/disabled
    """
    return _taxonomy_system


def is_taxonomy_system_enabled() -> bool:
    """
    Check if taxonomy system is enabled

    Returns:
        True if USE_DB_TAXONOMY=true and system is initialized
    """
    return _taxonomy_system is not None
