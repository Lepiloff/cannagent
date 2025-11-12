"""
Context Builder - Build LLM context with DB taxonomy data

Purpose:
- Format taxonomy data for LLM prompt
- Support both EN and ES languages
- Keep prompt concise (token efficiency)
- Include relevant statistics
- Build session context for follow-up queries

Design Principles:
- Single Responsibility: ONLY builds context
- Dependency Inversion: Depends on ITaxonomyCache interface
- Token efficient formatting

Performance:
- Cache hit: <5ms (from Redis/in-memory)
- Formatted context: ~2-3KB tokens
"""

from typing import Dict, Any, Optional, List
import logging

from app.core.taxonomy_cache import ITaxonomyCache

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Build context for LLM with DB taxonomy

    Responsibilities:
    - Load taxonomy from cache
    - Format for LLM prompt (comma-separated lists)
    - Add session context (conversation history, recommended strains)
    - Calculate statistics

    Design Decisions:
    - ALL taxonomy values included (not truncated!)
    - Comma-separated for LLM readability
    - Language-specific data from cache
    - Includes statistics for debugging
    - Session summary for context-aware queries
    """

    def __init__(self, taxonomy_cache: ITaxonomyCache):
        """
        Args:
            taxonomy_cache: Taxonomy cache instance
        """
        self.taxonomy_cache = taxonomy_cache
        logger.debug("ContextBuilder initialized")

    def build_llm_context(
        self,
        user_query: str,
        language: str = "es",
        session_context: Optional[Dict[str, Any]] = None,
        found_strains: Optional[List[Dict[str, Any]]] = None,
        fallback_used: bool = False
    ) -> Dict[str, Any]:
        """
        Build complete context for LLM query analysis

        Args:
            user_query: User's query string
            language: Language code ("en" or "es")
            session_context: Session context with history
            found_strains: Found strains for re-analysis
            fallback_used: Whether fallback was used

        Returns:
            {
                "user_query": "...",
                "language": "es",
                "available_flavors": "tropical, citrus, earthy, ...",
                "available_feelings": "relaxed, sleepy, happy, ...",
                "available_helps_with": "pain, anxiety, stress, ...",
                "available_negatives": "dry mouth, paranoia, ...",
                "available_terpenes": "Myrcene, Limonene, ...",
                "thc_range": "0-28%",
                "cbd_range": "0-15%",
                "categories": "Indica, Sativa, Hybrid",
                "session_summary": "...",
                "recommended_strains": "...",
                "fallback_note": "...",
                "stats": {...}
            }
        """
        # Get cached taxonomy (fast: <5ms)
        taxonomy = self.taxonomy_cache.get_taxonomy(language)

        # Build base context
        context = {
            "user_query": user_query,
            "language": language,

            # DB characteristics (ALL values, comma-separated)
            "available_flavors": ", ".join(taxonomy["flavors"]),
            "available_feelings": ", ".join(taxonomy["feelings"]),
            "available_helps_with": ", ".join(taxonomy["helps_with"]),
            "available_negatives": ", ".join(taxonomy["negatives"]),
            "available_terpenes": ", ".join(taxonomy["terpenes"]),

            # Ranges (from actual strain data)
            "thc_range": self._format_range(taxonomy["thc_range"]),
            "cbd_range": self._format_range(taxonomy["cbd_range"]),

            # Categories
            "categories": ", ".join(taxonomy["categories"]),

            # Statistics (for debugging/logging)
            "stats": taxonomy["stats"]
        }

        # Add session context if available
        if session_context:
            context["session_summary"] = self._build_session_summary(session_context)
            context["recommended_strains"] = session_context.get("recommended_strains", "None")
        else:
            context["session_summary"] = "No previous conversation"
            context["recommended_strains"] = "None"

        # Add found strains if available (for re-analysis)
        if found_strains:
            context["found_strains"] = self._format_found_strains(found_strains)
        else:
            context["found_strains"] = "None"

        # Add fallback notice if used
        if fallback_used:
            if language == "es":
                context["fallback_note"] = "Nota: No se encontró coincidencia exacta. Mostrando alternativas más cercanas."
            else:
                context["fallback_note"] = "Note: Exact match not found. Showing closest alternatives."
        else:
            context["fallback_note"] = ""

        logger.debug(
            f"Built LLM context: {len(taxonomy['flavors'])} flavors, "
            f"{len(taxonomy['feelings'])} feelings, "
            f"{len(taxonomy['helps_with'])} medical uses"
        )

        return context

    def _format_range(self, range_dict: Dict[str, float]) -> str:
        """
        Format range dict to string

        Args:
            range_dict: {"min": 0.5, "max": 28.3}

        Returns:
            "0.5-28.3%"
        """
        return f"{range_dict['min']:.1f}-{range_dict['max']:.1f}%"

    def _build_session_summary(self, session_context: Dict[str, Any]) -> str:
        """
        Build concise session summary

        Args:
            session_context: Session context dict

        Returns:
            "User: show me indica | User: which one has lowest thc"
        """
        history = session_context.get("conversation_history", [])
        if not history:
            return "No previous conversation"

        # Last 2 queries for context
        recent = history[-2:]
        summary = " | ".join([
            f"User: {entry.get('query', '')[:40]}"
            for entry in recent
        ])

        return summary

    def _format_found_strains(self, found_strains: List[Dict[str, Any]]) -> str:
        """
        Format found strains for LLM context

        Args:
            found_strains: List of strain dicts

        Returns:
            "Northern Lights (Indica, 18% THC), 9 lb Hammer (Indica, 20% THC), ..."
        """
        formatted = []
        for strain in found_strains[:5]:  # Top 5
            name = strain.get("name", "Unknown")
            category = strain.get("category", "")
            thc = strain.get("thc", "N/A")

            formatted.append(f"{name} ({category}, {thc}% THC)")

        return ", ".join(formatted)

    def build_prompt_section(self, context: Dict[str, Any]) -> str:
        """
        Build formatted prompt section for LLM

        Args:
            context: Context dict from build_llm_context()

        Returns:
            Formatted prompt section with DB context

        Example:
            ```
            DATABASE CONTEXT (use ONLY these values):
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Available Flavors: menthol, peppermint, tropical, citrus, ...
            Available Feelings: relaxed, sleepy, happy, energetic, ...
            Available Medical Uses: pain, anxiety, stress, insomnia, ...
            Available Terpenes: Myrcene, Limonene, Pinene, ...
            THC Range in DB: 0.5-28.3%
            CBD Range in DB: 0.1-15.2%
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            ```
        """
        section = f"""DATABASE CONTEXT (use ONLY these values for extraction):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Available Flavors: {context['available_flavors']}
Available Feelings: {context['available_feelings']}
Available Medical Uses: {context['available_helps_with']}
Available Negatives: {context['available_negatives']}
Available Terpenes: {context['available_terpenes']}

THC Range in DB: {context['thc_range']}
CBD Range in DB: {context['cbd_range']}
Categories: {context['categories']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER CONTEXT:
User query: "{context['user_query']}"
Language: {context['language']}
Session summary: {context['session_summary']}
Recommended strains: {context['recommended_strains']}
{context['fallback_note']}

CRITICAL INSTRUCTION:
When extracting attributes (flavors, effects, medical uses), you MUST map user input to values from the DATABASE CONTEXT above.

EXAMPLE 1 - User says "mint", DB has "menthol":
User: "show me strains with mint flavor"
→ Check "Available Flavors": contains "menthol, peppermint, spearmint" (similar to mint)
→ Extract: required_flavors=["menthol", "peppermint", "spearmint"]  ✅ CORRECT

EXAMPLE 2 - User says "high CBD", DB range is 0-15%:
User: "high CBD strains"
→ Check "CBD Range in DB": 0-15%
→ High CBD in this DB means ≥10%
→ Extract: cbd_level="high"  ✅ CORRECT

EXAMPLE 3 - User says "lemon", DB has "limonene":
User: "lemony strains"
→ Check "Available Flavors": contains "lemon, citrus" AND "Available Terpenes": contains "Limonene"
→ Extract: required_flavors=["lemon", "citrus"], required_terpenes=["Limonene"]  ✅ CORRECT
"""
        return section


# Factory function for dependency injection
def create_context_builder(taxonomy_cache: ITaxonomyCache) -> ContextBuilder:
    """
    Create ContextBuilder instance

    Args:
        taxonomy_cache: Taxonomy cache instance

    Returns:
        ContextBuilder instance
    """
    return ContextBuilder(taxonomy_cache)
