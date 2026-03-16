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

# Filler phrases that carry no search intent — removing them improves cache hit rate.
# e.g. "please show me indica" and "show me indica" → same cache key.
# Longer multi-word patterns must come before shorter ones to match greedily.
_FILLER_EN = re.compile(
    r"\b("
    # Polite hedges
    r"please|kindly|if possible|if you can"
    # Want/need (multi-word first)
    r"|i'm looking for|i am looking for|i'm searching for|i'm interested in"
    r"|i was wondering about|i was wondering if|i was hoping for"
    r"|i would like|i'd like|i wanna|i want to|i want"
    r"|i need to find|i need"
    r"|looking for|searching for|interested in"
    # Command verbs (multi-word first)
    r"|can you please|could you please|would you please"
    r"|can you|could you|would you|will you"
    r"|help me find|help me choose|help me pick"
    r"|show me|give me|find me|get me|bring me"
    r"|recommend me|suggest me"
    r"|hook me up with|point me to"
    r"|tell me about|tell me"
    # Question frames (multi-word first)
    r"|what would you suggest|what would you recommend"
    r"|what do you suggest|what do you recommend"
    r"|what do you have|do you have|do you know|do you carry"
    r"|is there any|are there any|is there|are there"
    r"|what are some|what about|how about"
    r"|any chance you have|by any chance"
    r"|got any|got something"
    # Conversational hedges
    r"|just looking for|just wondering"
    r"|something like|sort of like"
    r"|any good|some good"
    r"|maybe|perhaps"
    r")\b",
    re.IGNORECASE,
)
_FILLER_ES = re.compile(
    r"\b("
    # Polite
    r"por favor|si puedes|si es posible"
    # Want/need (multi-word first)
    r"|me gustaría|me gustaria|quisiera"
    r"|estoy buscando|ando buscando"
    r"|me interesa|me interesan"
    r"|quiero|necesito|busco"
    # Command verbs (multi-word first)
    r"|ayúdame a encontrar|ayudame a encontrar"
    r"|ayúdame a elegir|ayudame a elegir"
    r"|ayúdame a buscar|ayudame a buscar"
    r"|qué me recomiendas|que me recomiendas"
    r"|qué me sugieres|que me sugieres"
    r"|me puedes mostrar|me puedes dar|me puedes enseñar"
    r"|puedes|podrías|podrias"
    r"|muéstrame|muestrame|enséñame|ensename"
    r"|recomiéndame|recomiendame|sugiéreme|sugiereme"
    r"|dame|dime|sugiere"
    # Question frames
    r"|qué tienes|que tienes|tienen|tienes"
    r"|hay algo|hay"
    r"|conoces|sabes de"
    # Hedges
    r"|alguna|algún|algunos|algunas"
    r"|tal vez|quizás|quizas"
    r")\b",
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
