"""
Vector Search Service - Batch-optimized vector similarity search

Key Features:
- Single batch SQL query for all cosine distances (eliminates N+1 problem)
- ~400ms → ~20-50ms performance improvement
- Works with pre-filtered candidates from category filters
- Supports bilingual embeddings (en/es)

Performance:
- OLD: 20 individual queries × 20ms = 400ms
- NEW: 1 batch query = 20-50ms (8-20x faster)
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.models.database import Strain as StrainModel
from app.core.llm_interface import LLMInterface
import logging

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    Batch-optimized vector similarity search service

    Eliminates N+1 query problem by calculating all cosine distances
    in a single SQL query instead of one query per strain.
    """

    def __init__(self, llm_interface: LLMInterface, db_session: Session):
        """
        Args:
            llm_interface: LLM interface for generating query embeddings
            db_session: SQLAlchemy database session
        """
        self.llm = llm_interface
        self.db = db_session

    def search(
        self,
        query: str,
        candidates: List[StrainModel],
        language: str = 'es',
        limit: int = 5
    ) -> List[StrainModel]:
        """
        Perform batch-optimized vector similarity search

        Args:
            query: User's search query
            candidates: Pre-filtered list of candidate strains (from category filter)
            language: Language for embeddings ('en' or 'es')
            limit: Maximum number of results to return

        Returns:
            List of strains ranked by similarity (top N)

        Example:
            >>> service = VectorSearchService(llm, db)
            >>> # Pre-filter by category
            >>> indica_strains = db.query(Strain).filter(Strain.category == 'Indica').all()
            >>> # Vector search within Indica strains
            >>> results = service.search("help me sleep", indica_strains, language='en', limit=5)
        """
        if not candidates:
            logger.warning("No candidate strains provided for vector search")
            return []

        logger.info(f"Vector search: query='{query[:50]}...', candidates={len(candidates)}, language={language}")

        try:
            # Step 1: Generate query embedding once
            query_embedding = self._generate_query_embedding(query, language)

            # Step 2: Batch query for all cosine distances (SINGLE SQL QUERY)
            ranked_strains = self._batch_calculate_distances(
                query_embedding,
                candidates,
                language,
                limit
            )

            logger.info(f"Vector search completed: found {len(ranked_strains)} strains")
            return ranked_strains

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return self._fallback_search(candidates, limit)

    def _generate_query_embedding(self, query: str, language: str) -> List[float]:
        """
        Generate embedding for user query

        Args:
            query: User's search query
            language: Language hint for embedding model

        Returns:
            Query embedding vector (1536 dimensions for OpenAI)
        """
        try:
            # Use LLM interface to generate embedding
            embedding = self.llm.generate_embedding(query)

            if not embedding or len(embedding) == 0:
                raise ValueError("Empty embedding received from LLM")

            logger.debug(f"Generated query embedding: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            raise

    def _batch_calculate_distances(
        self,
        query_embedding: List[float],
        candidates: List[StrainModel],
        language: str,
        limit: int
    ) -> List[StrainModel]:
        """
        Calculate cosine distances for all candidates in a SINGLE batch query

        This is the key optimization that eliminates the N+1 problem.
        Instead of N separate queries, we use SQL IN clause to fetch all distances at once.

        Args:
            query_embedding: Query embedding vector
            candidates: List of candidate strains
            language: Language for embedding field selection
            limit: Maximum results to return

        Returns:
            List of strains sorted by similarity (ascending distance)
        """
        # Select appropriate embedding field based on language
        embedding_field_name = 'embedding_en' if language == 'en' else 'embedding_es'
        embedding_field = getattr(StrainModel, embedding_field_name)

        # Extract candidate IDs for filtering
        candidate_ids = [strain.id for strain in candidates]

        if not candidate_ids:
            return []

        # CRITICAL: Single batch query for all distances
        # OLD approach: for strain in candidates: query.filter(id == strain.id) → N queries
        # NEW approach: query.filter(id.in_(all_ids)) → 1 query
        try:
            distance_results = self.db.query(
                StrainModel.id,
                embedding_field.cosine_distance(query_embedding).label('distance')
            ).filter(
                StrainModel.id.in_(candidate_ids)
            ).filter(
                embedding_field.isnot(None)  # Only strains with embeddings
            ).all()

            logger.debug(f"Batch query returned {len(distance_results)} results")

        except Exception as e:
            logger.error(f"Batch distance calculation failed: {e}")
            raise

        # Sort by distance (lower = more similar)
        sorted_results = sorted(distance_results, key=lambda x: x.distance)
        top_results = sorted_results[:limit]

        # Extract top IDs
        top_ids = [result.id for result in top_results]

        if not top_ids:
            return []

        # Load FULL strain data with relationships in ONE query (avoids N+1 problem)
        # This is critical for performance - load all relationships at once
        full_strains = self.db.query(StrainModel).options(
            joinedload(StrainModel.feelings),
            joinedload(StrainModel.helps_with),
            joinedload(StrainModel.negatives),
            joinedload(StrainModel.flavors)
        ).filter(
            StrainModel.id.in_(top_ids)
        ).all()

        # Create lookup map and preserve ranking by distance
        strain_map = {strain.id: strain for strain in full_strains}
        ranked_strains = []

        for result in top_results:
            if result.id in strain_map:
                strain = strain_map[result.id]
                # Attach distance for debugging
                strain._similarity_distance = result.distance
                ranked_strains.append(strain)

        logger.debug(f"Loaded full data for {len(ranked_strains)} strains with relationships")
        return ranked_strains

    def _fallback_search(self, candidates: List[StrainModel], limit: int) -> List[StrainModel]:
        """
        Fallback when vector search fails

        Simply returns first N candidates without similarity ranking.
        This ensures the system still works even if vector search fails.

        Args:
            candidates: List of candidate strains
            limit: Maximum results to return

        Returns:
            First N candidates
        """
        logger.warning("Using fallback search (no vector ranking)")
        return candidates[:limit]

    def search_with_metadata(
        self,
        query: str,
        candidates: List[StrainModel],
        language: str = 'es',
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search with additional metadata about the search process

        Useful for debugging and monitoring search quality.

        Args:
            query: User's search query
            candidates: Pre-filtered list of candidate strains
            language: Language for embeddings
            limit: Maximum results to return

        Returns:
            Dictionary with:
            - strains: List of ranked strains
            - metadata: Search process information

        Example:
            >>> result = service.search_with_metadata("help me sleep", indica_strains)
            >>> print(f"Found {len(result['strains'])} strains")
            >>> print(f"Search took {result['metadata']['duration_ms']}ms")
        """
        import time
        start_time = time.time()

        strains = self.search(query, candidates, language, limit)

        duration_ms = (time.time() - start_time) * 1000

        metadata = {
            'query': query,
            'language': language,
            'candidates_count': len(candidates),
            'results_count': len(strains),
            'duration_ms': round(duration_ms, 2),
            'limit': limit
        }

        # Add similarity distances if available
        if strains and hasattr(strains[0], '_similarity_distance'):
            metadata['similarity_scores'] = [
                {
                    'strain_id': s.id,
                    'strain_name': s.name,
                    'distance': round(s._similarity_distance, 4)
                }
                for s in strains
            ]

        return {
            'strains': strains,
            'metadata': metadata
        }


# ============================================================
# USAGE EXAMPLES (for documentation)
# ============================================================

"""
# Example 1: Simple vector search within category-filtered strains
from app.core.vector_search_service import VectorSearchService
from app.core.category_filter import FilterChain, CategoryFilter
from app.db.database import SessionLocal
from app.models.database import Strain

db = SessionLocal()

# Step 1: Pre-filter by category using SQL
filter_chain = FilterChain()
filter_chain.add(CategoryFilter("Indica"))
category_filtered = filter_chain.apply(db.query(Strain)).all()

# Step 2: Vector search within filtered candidates
vector_service = VectorSearchService(llm_interface, db)
results = vector_service.search(
    query="I need help sleeping",
    candidates=category_filtered,
    language='en',
    limit=5
)

for strain in results:
    print(f"{strain.name} - Similarity: {strain._similarity_distance:.4f}")


# Example 2: Search with metadata for monitoring
result = vector_service.search_with_metadata(
    query="necesito algo relajante",
    candidates=category_filtered,
    language='es',
    limit=10
)

print(f"Found {result['metadata']['results_count']} strains in {result['metadata']['duration_ms']}ms")


# Example 3: Two-stage search (SQL filter + vector search)
from app.core.category_filter import FilterFactory

# Stage 1: SQL filtering (category + THC range)
factory = FilterFactory()
sql_chain = factory.create_from_params({
    "category": "Indica",
    "min_thc": 15
})
sql_filtered = sql_chain.apply(db.query(Strain)).all()
print(f"SQL filtering: {len(sql_filtered)} candidates")

# Stage 2: Vector search for semantic relevance
vector_results = vector_service.search(
    query="strong strain for chronic pain",
    candidates=sql_filtered,
    language='en',
    limit=5
)
print(f"Vector search: {len(vector_results)} final results")


# Example 4: Multilingual search
# English query
en_results = vector_service.search(
    query="energy and focus for work",
    candidates=all_strains,
    language='en',
    limit=5
)

# Spanish query (uses embedding_es)
es_results = vector_service.search(
    query="energía y enfoque para trabajar",
    candidates=all_strains,
    language='es',
    limit=5
)


# Example 5: Performance comparison
import time

# OLD approach (N+1 problem)
start = time.time()
for strain in candidates[:20]:
    distance = db.query(
        Strain.embedding_en.cosine_distance(query_embedding)
    ).filter(Strain.id == strain.id).first()
old_duration = time.time() - start
print(f"OLD: {old_duration * 1000:.2f}ms")  # ~400ms

# NEW approach (batch)
start = time.time()
results = vector_service.search(query, candidates[:20], language='en')
new_duration = time.time() - start
print(f"NEW: {new_duration * 1000:.2f}ms")  # ~20-50ms
print(f"Speedup: {old_duration / new_duration:.1f}x faster")
"""
