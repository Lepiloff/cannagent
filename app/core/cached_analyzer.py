"""
Cached Query Analyzer — transparent caching decorator for StreamlinedQueryAnalyzer.

Caches QueryAnalysis results in Redis for identical queries (same text + language).
Only caches context-free queries (new searches). Follow-ups and context-dependent
queries always go to the LLM.
"""

import hashlib
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from app.core.streamlined_analyzer import StreamlinedQueryAnalyzer, QueryAnalysis

logger = logging.getLogger(__name__)

# Filler phrases that carry no search intent — removing them improves cache hit rate
# e.g. "please show me indica" and "show me indica" → same cache key
_FILLER_EN = re.compile(
    r"\b(please|can you|could you|i want|i need|i'm looking for|"
    r"show me|give me|find me|recommend me|suggest me|help me find|"
    r"do you have|what do you have|i'd like)\b",
    re.IGNORECASE,
)
_FILLER_ES = re.compile(
    r"\b(por favor|puedes|podrías|quiero|necesito|busco|"
    r"dame|muéstrame|muéstrame|recomiéndame|sugiere|ayúdame a encontrar|"
    r"tienes|qué tienes|me gustaría|quisiera)\b",
    re.IGNORECASE,
)
_PUNCTUATION = re.compile(r"[^\w\s]")


class CachedQueryAnalyzer:
    """Transparent caching wrapper around StreamlinedQueryAnalyzer.

    Delegates all methods to the wrapped analyzer, adding Redis caching
    for aanalyze_query on context-free new searches.
    """

    def __init__(self, analyzer: StreamlinedQueryAnalyzer, cache_service):
        self._analyzer = analyzer
        self._cache = cache_service

    # -- Proxied attributes (so SmartRAGService can access them) --
    @property
    def llm(self):
        return self._analyzer.llm

    @property
    def context_builder(self):
        return self._analyzer.context_builder

    def _build_cache_key(
        self, query: str, language: str, has_session_context: bool
    ) -> Optional[str]:
        """Build cache key or return None if query should not be cached.

        Cache rules:
        - Only cache queries WITHOUT session context (new searches)
        - Normalize: lowercase, strip, collapse whitespace
        """
        if has_session_context:
            return None
        q = query.lower().strip()
        q = _FILLER_EN.sub("", q)
        q = _FILLER_ES.sub("", q)
        q = _PUNCTUATION.sub("", q)
        normalized = " ".join(q.split())
        query_hash = hashlib.md5(normalized.encode()).hexdigest()
        return f"analysis:{language}:{query_hash}"

    async def aanalyze_query(
        self,
        user_query: str,
        session_context: Optional[Dict[str, Any]] = None,
        found_strains: Optional[List[Dict[str, Any]]] = None,
        fallback_used: bool = False,
        explicit_language: Optional[str] = None,
    ) -> QueryAnalysis:
        language = explicit_language or "es"

        # Determine if we have meaningful session context
        has_context = bool(
            session_context
            and session_context.get("conversation_history")
        )

        cache_key = self._build_cache_key(user_query, language, has_context)

        # Try cache
        if cache_key:
            try:
                cached = await self._cache.get_analysis(cache_key)
                if cached is not None:
                    logger.info(f"Analysis cache hit for '{user_query[:40]}...'")
                    return QueryAnalysis(**cached)
            except Exception as e:
                logger.warning(f"Analysis cache read failed: {e}")

        # Cache miss — run actual analysis
        result = await self._analyzer.aanalyze_query(
            user_query=user_query,
            session_context=session_context,
            found_strains=found_strains,
            fallback_used=fallback_used,
            explicit_language=explicit_language,
        )

        # Cache result (only for context-free queries)
        if cache_key and result:
            try:
                await self._cache.set_analysis(cache_key, result.dict())
            except Exception as e:
                logger.warning(f"Analysis cache write failed: {e}")

        return result

    # -- Pass-through methods (no caching needed) --

    def analyze_query(self, *args, **kwargs) -> QueryAnalysis:
        return self._analyzer.analyze_query(*args, **kwargs)

    def generate_response_only(self, *args, **kwargs) -> str:
        return self._analyzer.generate_response_only(*args, **kwargs)

    async def agenerate_response_only(self, *args, **kwargs) -> str:
        return await self._analyzer.agenerate_response_only(*args, **kwargs)

    async def astream_response_only(self, *args, **kwargs):
        async for chunk in self._analyzer.astream_response_only(*args, **kwargs):
            yield chunk
