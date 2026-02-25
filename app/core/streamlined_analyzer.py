"""
Streamlined Query Analyzer - Упрощённая версия для векторного поиска

Основная задача:
1. Определить категорию сорта (Indica/Sativa/Hybrid) если упомянута
2. Сгенерировать качественный естественный ответ
3. Предложить follow-up действия

Векторный поиск - ОСНОВНОЙ метод поиска. SQL только для категории.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, validator
from app.core.llm_interface import LLMInterface

if TYPE_CHECKING:
    from app.core.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


class FollowUpIntent(BaseModel):
    """
    Structured intent for follow-up queries.
    Extracted by LLM but executed deterministically.
    """
    action: Literal["compare", "filter", "sort", "select", "describe"] = Field(
        default="describe",
        description="Action to perform: compare, filter, sort, select, describe"
    )
    field: Optional[str] = Field(
        None,
        description="Field to operate on: thc, cbd, category"
    )
    order: Optional[Literal["asc", "desc"]] = Field(
        None,
        description="Sort order for compare/sort"
    )
    filter_value: Optional[str] = Field(
        None,
        description="Value to filter by"
    )
    strain_indices: Optional[List[int]] = Field(
        None,
        description="Strain indices for select (0-based)"
    )


class QueryAnalysis(BaseModel):
    """Результат упрощённого анализа запроса"""
    detected_category: Optional[str] = Field(None, description="Категория сорта: Indica/Sativa/Hybrid или None")
    thc_level: Optional[str] = Field(None, description="Уровень THC: low/medium/high или None")
    cbd_level: Optional[str] = Field(None, description="Уровень CBD: low/medium/high или None")

    # Query intent detection (CRITICAL for avoiding unnecessary searches)
    is_search_query: bool = Field(default=True, description="Whether user is requesting strain search/recommendation")

    # Specific strain query detection (return only 1 strain, not 5 similar)
    specific_strain_name: Optional[str] = Field(None, description="Exact strain name if user asks about specific strain")

    # Follow-up query detection
    is_follow_up: bool = Field(default=False, description="Whether this is a follow-up query referencing previous results")

    # NEW: Structured follow-up intent for deterministic execution
    follow_up_intent: Optional[FollowUpIntent] = Field(
        None,
        description="Structured intent for follow-up queries (used for deterministic execution)"
    )

    # Exact attribute extraction for SQL pre-filtering (PostgreSQL fuzzy matching)
    required_flavors: Optional[List[str]] = Field(None, description="Flavors mentioned (as written): ['tropical', 'citrus']")
    required_effects: Optional[List[str]] = Field(None, description="Effects mentioned (as written): ['relaxed', 'sleepy']")
    required_helps_with: Optional[List[str]] = Field(None, description="Medical uses (as written): ['pain', 'anxiety']")
    exclude_negatives: Optional[List[str]] = Field(None, description="Side effects to avoid (as written): ['paranoia', 'anxiety']")
    required_terpenes: Optional[List[str]] = Field(None, description="Terpenes mentioned (as written): ['myrcene', 'limonene']")

    natural_response: str = Field(..., description="Естественный ответ пользователю")
    suggested_follow_ups: List[str] = Field(default_factory=list, description="Предлагаемые follow-up действия")
    detected_language: str = Field(default="es", description="Обнаруженный язык (es|en)")
    confidence: float = Field(default=0.9, description="Уверенность в анализе (0.0-1.0)")

    @validator('detected_category')
    def validate_category(cls, v):
        if v is None:
            return None
        v = str(v).strip().capitalize()
        if v.lower() == "null" or v == "":
            return None
        if v not in ["Indica", "Sativa", "Hybrid"]:
            return None
        return v

    @validator('confidence')
    def validate_confidence(cls, v):
        return max(0.0, min(1.0, float(v)))


class StreamlinedQueryAnalyzer:
    """
    Упрощённый Query Analyzer для векторного поиска

    Принцип: Минимум промпта, максимум качества
    - Детекция категории через LLM (расширяемо)
    - Векторный поиск как основной метод
    - Качественный natural response
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        context_builder: Optional["ContextBuilder"] = None
    ):
        """
        Args:
            llm_interface: LLM interface for query analysis
            context_builder: Context builder with DB taxonomy (optional for graceful degradation)
        """
        self.llm = llm_interface
        self.context_builder = context_builder

        if not context_builder:
            logger.warning(
                "StreamlinedQueryAnalyzer initialized without ContextBuilder - "
                "using hardcoded taxonomy data (not recommended)"
            )

    def generate_response_only(
        self,
        query: str,
        strains: List[Dict[str, Any]],
        language: str = "en"
    ) -> str:
        """
        FIX-003: Mini-prompt for re-analysis.
        Generates ONLY natural_response without full analysis.
        ~10x smaller prompt = ~3-4x faster.
        """
        strain_info = ", ".join([
            f"{s.get('name', '?')} ({s.get('category', '?')}, {s.get('thc', '?')}% THC)"
            for s in strains[:5]
        ])

        if language == "es":
            prompt = f"""Eres un budtender experto. Genera una respuesta breve.
Consulta: "{query}"
Cepas: {strain_info}
Escribe 2-3 oraciones recomendando estas cepas. Menciona 1-2 por nombre.
Respuesta:"""
        else:
            prompt = f"""You are an expert cannabis budtender. Generate a helpful response.
Query: "{query}"
Strains: {strain_info}
Write 2-3 sentences recommending these strains. Mention 1-2 by name.
Response:"""

        try:
            response = self.llm.generate_response(prompt)
            response = response.strip()
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]
            return response
        except Exception as e:
            logger.warning(f"Mini-prompt failed: {e}")
            if strains:
                first = strains[0].get('name', 'this strain')
                if language == "es":
                    return f"Te recomiendo {first}. Es una excelente opción."
                return f"I recommend {first}. It's a great option for you."
            return "I found some great options for you!"

    async def agenerate_response_only(
        self,
        query: str,
        strains: List[Dict[str, Any]],
        language: str = "en"
    ) -> str:
        """Async version of generate_response_only: uses native async LLM call."""
        strain_info = ", ".join([
            f"{s.get('name', '?')} ({s.get('category', '?')}, {s.get('thc', '?')}% THC)"
            for s in strains[:5]
        ])

        if language == "es":
            prompt = f"""Eres un budtender experto. Genera una respuesta breve.
Consulta: "{query}"
Cepas: {strain_info}
Escribe 2-3 oraciones recomendando estas cepas. Menciona 1-2 por nombre.
Respuesta:"""
        else:
            prompt = f"""You are an expert cannabis budtender. Generate a helpful response.
Query: "{query}"
Strains: {strain_info}
Write 2-3 sentences recommending these strains. Mention 1-2 by name.
Response:"""

        try:
            response = await self.llm.agenerate_response(prompt)
            response = response.strip()
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]
            return response
        except Exception as e:
            logger.warning(f"Async mini-prompt failed: {e}")
            if strains:
                first = strains[0].get('name', 'this strain')
                if language == "es":
                    return f"Te recomiendo {first}. Es una excelente opción."
                return f"I recommend {first}. It's a great option for you."
            return "I found some great options for you!"

    def _build_mini_prompt(self, query: str, strains: List[Dict[str, Any]], language: str) -> str:
        """Build the mini-prompt for response generation (shared by sync/async/streaming)."""
        strain_info = ", ".join([
            f"{s.get('name', '?')} ({s.get('category', '?')}, {s.get('thc', '?')}% THC)"
            for s in strains[:5]
        ])
        if language == "es":
            return f"""Eres un budtender experto. Genera una respuesta breve.
Consulta: "{query}"
Cepas: {strain_info}
Escribe 2-3 oraciones recomendando estas cepas. Menciona 1-2 por nombre.
Respuesta:"""
        else:
            return f"""You are an expert cannabis budtender. Generate a helpful response.
Query: "{query}"
Strains: {strain_info}
Write 2-3 sentences recommending these strains. Mention 1-2 by name.
Response:"""

    async def astream_response_only(
        self,
        query: str,
        strains: List[Dict[str, Any]],
        language: str = "en"
    ) -> "AsyncIterator[str]":
        """Streaming version of agenerate_response_only — yields text chunks."""
        prompt = self._build_mini_prompt(query, strains, language)
        try:
            async for chunk in self.llm.astream_response(prompt):
                yield chunk
        except Exception as e:
            logger.warning(f"Streaming mini-prompt failed: {e}")
            if strains:
                first = strains[0].get('name', 'this strain')
                if language == "es":
                    yield f"Te recomiendo {first}. Es una excelente opción."
                else:
                    yield f"I recommend {first}. It's a great option for you."
            else:
                yield "I found some great options for you!"

    def analyze_query(
        self,
        user_query: str,
        session_context: Optional[Dict[str, Any]] = None,
        found_strains: Optional[List[Dict[str, Any]]] = None,
        fallback_used: bool = False,
        explicit_language: Optional[str] = None
    ) -> QueryAnalysis:
        """
        Главный метод анализа запроса

        Args:
            user_query: Запрос пользователя
            session_context: Контекст сессии (опционально)
            found_strains: Найденные сорта для формирования ответа (опционально)

        Returns:
            QueryAnalysis с категорией и natural response
        """
        logger.info(f"Streamlined analysis for query: {user_query[:50]}... (language={explicit_language})")

        try:
            # Формируем минимальный контекст
            context = self._build_context(
                user_query,
                session_context,
                found_strains,
                fallback_used,
                explicit_language=explicit_language
            )

            # Анализ через LLM
            raw_result = self._analyze_with_llm(context, explicit_language)

            # Парсинг результата
            analysis = self._parse_result(raw_result, user_query, explicit_language)

            logger.info(f"Analysis completed: category={analysis.detected_category}, language={analysis.detected_language}")
            return analysis

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return self._fallback_analysis(user_query, explicit_language)

    async def aanalyze_query(
        self,
        user_query: str,
        session_context: Optional[Dict[str, Any]] = None,
        found_strains: Optional[List[Dict[str, Any]]] = None,
        fallback_used: bool = False,
        explicit_language: Optional[str] = None
    ) -> QueryAnalysis:
        """Async version of analyze_query: uses native async LLM call."""
        logger.info(f"Async streamlined analysis for query: {user_query[:50]}... (language={explicit_language})")

        try:
            # Build context (sync — pure computation, no I/O)
            context = self._build_context(
                user_query, session_context, found_strains,
                fallback_used, explicit_language=explicit_language
            )

            # Async LLM analysis
            raw_result = await self._aanalyze_with_llm(context, explicit_language)

            # Parse result (sync — pure computation)
            analysis = self._parse_result(raw_result, user_query, explicit_language)

            logger.info(f"Async analysis completed: category={analysis.detected_category}, language={analysis.detected_language}")
            return analysis

        except Exception as e:
            logger.error(f"Async analysis failed: {e}", exc_info=True)
            return self._fallback_analysis(user_query, explicit_language)

    def _build_context(
        self,
        user_query: str,
        session_context: Optional[Dict[str, Any]],
        found_strains: Optional[List[Dict[str, Any]]],
        fallback_used: bool = False,
        explicit_language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Построение минимального контекста для LLM"""

        # Explicit language takes priority over session language (mirrors SmartRAGService logic)
        target_language = explicit_language if explicit_language in ["en", "es"] else None

        # Базовый контекст
        context = {
            "user_query": user_query,
            "has_session": session_context is not None and len(session_context.get("conversation_history", [])) > 0,
            "conversation_summary": "",
            "previous_language": target_language or "es",
            "target_language": target_language or "es",
            "fallback_note": "Note: Exact match not found. Showing closest alternatives." if fallback_used else ""
        }

        # Добавляем краткую историю диалога если есть
        if session_context:
            conversation_history = session_context.get("conversation_history", [])
            if conversation_history:
                recent = conversation_history[-2:]  # Последние 2 сообщения
                context["conversation_summary"] = " | ".join([
                    f"User: {entry.get('query', '')[:40]}"
                    for entry in recent
                ])
                if not target_language:
                    context["previous_language"] = session_context.get("detected_language", "es")
                    context["target_language"] = context["previous_language"]

            # Получаем recommended_strains из session_context если есть
            recommended_strains = session_context.get("recommended_strains", [])
            if recommended_strains:
                # Преобразуем список в читаемую строку
                context["recommended_strains"] = ", ".join(recommended_strains)
            else:
                context["recommended_strains"] = "None"
        else:
            context["recommended_strains"] = "None"

        # Добавляем найденные сорта для формирования ответа
        if found_strains:
            # Краткая информация о сортах (только имена и основные характеристики)
            strain_summaries = []
            for strain in found_strains[:5]:  # Топ-5 сортов
                summary = f"{strain.get('name')} ({strain.get('category')}, THC: {strain.get('thc')}%)"
                strain_summaries.append(summary)
            context["recommended_strains"] = ", ".join(strain_summaries)

        return context

    def _build_db_context_section(self, context: Dict[str, Any], target_language: str) -> str:
        """Build DB taxonomy context section for prompts."""
        if self.context_builder:
            try:
                llm_context = self.context_builder.build_llm_context(
                    user_query=context["user_query"],
                    language=target_language,
                    session_context=None,
                    found_strains=None,
                    fallback_used=bool(context.get("fallback_note"))
                )
                db_context_section = self.context_builder.build_db_context_section(llm_context)
                logger.debug("Using dynamic DB taxonomy context from ContextBuilder")
                return db_context_section
            except Exception as e:
                logger.warning(f"Failed to build DB context: {e}. Using fallback.")
                return self._build_fallback_db_context()
        else:
            logger.debug("ContextBuilder not available - using hardcoded taxonomy")
            return self._build_fallback_db_context()

    def _analyze_with_llm(self, context: Dict[str, Any], explicit_language: Optional[str] = None) -> Dict[str, Any]:
        """Анализ через LLM с раздельными system/user промптами для prompt caching."""

        target_language = explicit_language or context.get("target_language", "es")

        db_context_section = self._build_db_context_section(context, target_language)

        # Build separate system (static, cached) and user (variable) prompts
        system_prompt = self._get_system_prompt_template().format(db_context=db_context_section)
        user_prompt = self._get_user_prompt_template().format(**context)

        try:
            response = self.llm.generate_response_with_system(system_prompt, user_prompt)
            result = self._extract_json_from_response(response)
            return result
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _get_system_prompt_template(self) -> str:
        """Returns the STATIC system prompt template (cached by OpenAI prompt caching).

        This template contains: role definition, DB taxonomy, analysis instructions,
        examples, and response format. It changes only when DB taxonomy updates
        or language switches (en↔es). OpenAI caches this automatically when >1024 tokens.
        """
        return """You are an expert cannabis budtender AI assistant.

{db_context}

TASK:
Analyze the user's query and provide:

0. **Query Intent Detection** (CRITICAL - determines if search is needed):

   **is_search_query = FALSE** if user is:
   - Greeting: "hello", "hi", "hey", "hola", "buenos días"
   - Asking for help: "how can you help", "what can you do", "help me", "ayúdame"
   - General questions: "what is cannabis", "how does THC work", "what are terpenes"
   - Thanking: "thank you", "thanks", "gracias"
   - Chitchat: "how are you", "what's up", "¿cómo estás"
   - Out of domain: politics, weather, news, sports, etc.

   **is_search_query = TRUE** if user is:
   - Requesting strains: "suggest", "recommend", "show me", "find", "recomienda", "muéstrame"
   - Describing needs: "for sleep", "for pain", "high thc", "para dormir", "relajante"
   - Asking about strains: "which strain", "what's good for", "cuál es el mejor"
   - Comparing strains: "which one has more THC", "difference between"

   **IMPORTANT**: Default to TRUE if unclear. Only set FALSE for clear non-search queries.

0.5. **Specific Strain Query Detection** (CRITICAL - determines if user asks about exact strain):

   **specific_strain_name = "Strain Name"** if user asks about a SPECIFIC strain:
   - "do you have info about Tropicana Cookies" → "Tropicana Cookies"
   - "tell me about Northern Lights" → "Northern Lights"
   - "what is Blue Dream" → "Blue Dream"
   - "información sobre ACDC" → "ACDC"
   - "tienes la cepa Harlequin" → "Harlequin"

   **specific_strain_name = null** if user wants RECOMMENDATIONS/SEARCH:
   - "suggest me indica strains" → null (searching, not specific)
   - "show me high THC strains" → null (searching)
   - "what's good for sleep" → null (recommendations)

   **IMPORTANT**:
   - Extract EXACT strain name as written by user (capitalization OK)
   - Only set if user clearly references ONE specific strain
   - If specific strain detected, return ONLY that strain (limit=1), not similar ones

1. **Category Detection** (for SQL pre-filtering):
   - If user mentions "indica", "sativa", or "hybrid" explicitly → return that category
   - If user describes effects that strongly suggest a category → return that category
     * "relax", "sleep", "calm", "evening", "dormir", "relajar" → Indica
     * "energy", "focus", "creative", "daytime", "energía", "creatividad" → Sativa
     * "balanced", "versatile", "equilibrado" → Hybrid
   - If NO clear category → return null
   - Valid values: "Indica", "Sativa", "Hybrid", or null

2. **THC Level Detection** (for SQL pre-filtering):
   - If user mentions THC level → return appropriate level
     * "low thc", "bajo thc", "mild", "suave", "beginners", "principiantes" → "low" (< 10%)
     * "medium thc", "medio thc", "moderate", "moderado" → "medium" (10-20%)
     * "high thc", "alto thc", "strong", "fuerte", "potent", "potente" → "high" (> 20%)
   - If NO THC level mentioned → return null
   - Valid values: "low", "medium", "high", or null

3. **CBD Level Detection** (for SQL pre-filtering):
   - If user mentions CBD level → return appropriate level
     * "low cbd", "bajo cbd" → "low" (< 3%)
     * "medium cbd", "medio cbd" → "medium" (3-10%)
     * "high cbd", "alto cbd", "medical", "medicinal" → "high" (≥ 10%)
   - If NO CBD level mentioned → return null
   - Valid values: "low", "medium", "high", or null

4. **Exact Attribute Extraction** (for SQL pre-filtering with fuzzy matching):
   Extract ONLY if explicitly mentioned by user. Write EXACTLY as user wrote (typos OK).
   PostgreSQL fuzzy matching will handle mapping to DB values.

   **IMPORTANT**: Refer to DATABASE CONTEXT above for available values!

   **Flavors** (required_flavors):
   - Extract if user mentions taste/flavor/aroma keywords
   - Examples: "tropical" → ["tropical"], "citrus mango" → ["citrus", "mango"]
   - Typos OK: "tropicas" → ["tropicas"], "mint" → ["mint"] (fuzzy match will find "menthol")
   - See "Available Flavors" in DATABASE CONTEXT for reference

   **Effects** (required_effects):
   - Extract if user mentions specific feelings/effects
   - Examples: "relaxed sleepy" → ["relaxed", "sleepy"], "energetic creative" → ["energetic", "creative"]
   - See "Available Feelings" in DATABASE CONTEXT for reference

   **Medical Uses** (required_helps_with):
   - Extract if user mentions medical conditions/symptoms
   - Examples: "for pain and anxiety" → ["pain", "anxiety"], "para dormir" → ["insomnia"]
   - See "Available Medical Uses" in DATABASE CONTEXT for reference

   **Exclude Negatives** (exclude_negatives):
   - Extract if user wants to AVOID side effects
   - Examples: "without paranoia" → ["paranoia"], "que no cause ansiedad" → ["anxiety"]
   - See "Available Negatives" in DATABASE CONTEXT for reference

   **Terpenes** (required_terpenes):
   - Extract ONLY if user explicitly mentions terpene names
   - Examples: "with myrcene" → ["myrcene"], "limonene pinene" → ["limonene", "pinene"]
   - See "Available Terpenes" in DATABASE CONTEXT for reference

   **IMPORTANT**:
   - Return empty array [] if not mentioned
   - Write EXACTLY as user wrote - fuzzy matching happens in SQL
   - DO NOT translate/localize extracted attributes; keep them as written by the user
   - DB context contains ALL available values - use it as reference!

5. **Follow-up Query Detection** (CRITICAL):

   **is_follow_up = TRUE** if ALL conditions:
   ✓ Previous strains exist in "Recommended strains"
   ✓ User operates on EXISTING results (compare/filter/sort/select)
   ✓ NO new search criteria introduced

   **is_follow_up = FALSE** if ANY:
   ✗ User introduces NEW criteria (different category, new effects, new flavors)
   ✗ User requests NEW search (suggest/find/show/recommend with new parameters)

5.5. **Follow-up Intent Extraction** (ONLY when is_follow_up=true):
   Extract structured intent for deterministic execution:

   **action** (required): "compare" | "filter" | "sort" | "select" | "describe"
   **field** (for compare/sort): "thc" | "cbd" | "category"
   **order** (for compare/sort): "asc" (lowest/mildest) | "desc" (highest/strongest)
   **filter_value** (for filter): "Indica" | "Sativa" | "Hybrid"
   **strain_indices** (for select): [0] for first, [1] for second, etc.

   **Intent Examples:**
   - "which has highest THC" → {{"action":"compare","field":"thc","order":"desc"}}
   - "which is mildest" → {{"action":"compare","field":"thc","order":"asc"}}
   - "show only indica" → {{"action":"filter","field":"category","filter_value":"Indica"}}
   - "the first one" → {{"action":"select","strain_indices":[0]}}
   - "tell me about them" → {{"action":"describe"}}

   **IMPORTANT**: When is_follow_up=true, natural_response is IGNORED.
   The system will use follow_up_intent to generate response deterministically.
   You can set natural_response to a placeholder like "Follow-up processed".

6. **Natural Response** (for NEW searches only):
   - Generate helpful, friendly response in the target language
   - If strains are recommended, explain WHY they fit the request
   - Mention 1-2 specific strains by name with brief explanation
   - Keep response concise (2-3 sentences)
   - Be conversational like a knowledgeable budtender

7. **Follow-up Suggestions**:
   - Suggest 2-3 relevant follow-up questions
   - Make them contextual to the user's query
   - Use the target language

CRITICAL GUIDELINES:
- Category is ONLY for pre-filtering - don't over-specify
- Vector search handles ALL relevance matching
- Focus on high-quality natural response
- Keep it simple and helpful
- **FOLLOW-UP DETECTION IS CRITICAL**: If user references previous results, set is_follow_up=true
- **LANGUAGE IS CRITICAL**: natural_response and suggested_follow_ups MUST be in the target language

⚠️ **ABSOLUTELY CRITICAL FOR FOLLOW-UP QUERIES**:
When is_follow_up=true, you MUST follow these rules for "natural_response":

1. **If query is about comparing/selecting from current list** (e.g., "which has lowest THC", "which is strongest", "show me the indica from that list"):
   - ONLY use strains from "Recommended strains" list
   - DO NOT mention ANY strains outside this list
   - Example: "Recommended strains" = [A (16% THC), B (19% THC)] + Query "which has lowest THC" → Answer: "A has the lowest THC at 16%"

2. **If current list has NO suitable options for the request** (e.g., user asks for Indica but list only has Sativa):
   - Set is_follow_up=false to trigger new search
   - Explain that current list doesn't match and suggest new search

3. **NEVER mention strains from general database knowledge when is_follow_up=true and suitable options exist in "Recommended strains"**

RESPONSE FORMAT (JSON only):
{{
  "is_search_query": true|false,
  "specific_strain_name": "Strain Name"|null,
  "detected_category": "Indica"|"Sativa"|"Hybrid"|null,
  "thc_level": "low"|"medium"|"high"|null,
  "cbd_level": "low"|"medium"|"high"|null,
  "is_follow_up": true|false,
  "follow_up_intent": {{"action":"compare|filter|sort|select|describe","field":"thc|cbd|category"|null,"order":"asc|desc"|null,"filter_value":"string"|null,"strain_indices":[0,1]|null}} or null,
  "required_flavors": ["flavor1"] or null,
  "required_effects": ["effect1"] or null,
  "required_helps_with": ["condition1"] or null,
  "exclude_negatives": ["negative1"] or null,
  "required_terpenes": ["terpene1"] or null,
  "natural_response": "Response text (ignored if is_follow_up=true)",
  "suggested_follow_ups": ["follow-up 1", "follow-up 2"],
  "confidence": 0.0-1.0
}}

EXAMPLES (6 key scenarios):

1. NON-SEARCH (greeting/help):
Query: "hey, how can you help me"
{{"is_search_query": false, "is_follow_up": false, "natural_response": "I'm your cannabis budtender! I can help you find strains for relaxation, energy, pain relief, or specific flavors.", "suggested_follow_ups": ["Relaxing strains", "For sleep", "For pain"], "confidence": 0.95}}

2. SEARCH with medical use:
Query: "which strains help with pain?"
{{"is_search_query": true, "is_follow_up": false, "detected_category": null, "required_helps_with": ["pain"], "natural_response": "For pain relief, I recommend indica strains with high THC or CBD options like ACDC.", "suggested_follow_ups": ["Indica or sativa?", "High CBD options?"], "confidence": 0.9}}

3. SEARCH with multiple filters:
Query: "suggest me indica with tropical flavor and high thc"
{{"is_search_query": true, "is_follow_up": false, "detected_category": "Indica", "thc_level": "high", "required_flavors": ["tropical"], "natural_response": "I'll find you an indica with tropical flavors and high THC.", "suggested_follow_ups": ["Something sweeter?", "Help with sleep?"], "confidence": 0.95}}

4. SPECIFIC STRAIN:
Query: "tell me about Northern Lights"
{{"is_search_query": true, "specific_strain_name": "Northern Lights", "is_follow_up": false, "natural_response": "Northern Lights is a classic indica with relaxing effects.", "suggested_follow_ups": ["Similar strains?", "Effects?"], "confidence": 0.95}}

5. FOLLOW-UP (compare):
Context: Recommended strains: Super Silver Haze (21% THC), Chocolope (22% THC)
Query: "which has higher THC"
{{"is_search_query": true, "is_follow_up": true, "follow_up_intent": {{"action": "compare", "field": "thc", "order": "desc"}}, "natural_response": "Follow-up processed", "suggested_follow_ups": ["Effects?", "CBD options?"], "confidence": 0.95}}

6. NOT FOLLOW-UP (new criteria):
Context: Recommended strains: G13 (Indica), Truffle (Hybrid)
Query: "now show me sativa strains for energy"
{{"is_search_query": true, "is_follow_up": false, "follow_up_intent": null, "detected_category": "Sativa", "required_effects": ["energetic"], "natural_response": "I'll find you energetic sativa strains.", "suggested_follow_ups": ["THC level?", "Flavor?"], "confidence": 0.95}}
"""

    def _get_user_prompt_template(self) -> str:
        """Returns the VARIABLE user prompt template (changes every request).

        Contains only user-specific context: query, language, session info.
        This is NOT cached — only the system prompt prefix is cached by OpenAI.
        """
        return """USER QUERY: "{user_query}"
TARGET LANGUAGE: {target_language}
PREVIOUS LANGUAGE: {previous_language}
CONVERSATION: {conversation_summary}
RECOMMENDED STRAINS: {recommended_strains}
{fallback_note}

Respond with JSON only."""

    async def _aanalyze_with_llm(self, context: Dict[str, Any], explicit_language: Optional[str] = None) -> Dict[str, Any]:
        """Async version of _analyze_with_llm with separate system/user prompts for prompt caching."""

        target_language = explicit_language or context.get("target_language", "es")

        db_context_section = self._build_db_context_section(context, target_language)

        # Build separate system (static, cached) and user (variable) prompts
        system_prompt = self._get_system_prompt_template().format(db_context=db_context_section)
        user_prompt = self._get_user_prompt_template().format(**context)

        try:
            response = await self.llm.agenerate_response_with_system(system_prompt, user_prompt)
            result = self._extract_json_from_response(response)
            return result
        except Exception as e:
            logger.error(f"Async LLM call failed: {e}")
            raise

    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Извлечение JSON из текстового ответа LLM"""
        try:
            # Ищем JSON блок в ответе
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1

            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in LLM response")

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to extract JSON: {e}")
            logger.debug(f"LLM response: {response}")
            raise

    def _parse_result(self, raw_result: Dict[str, Any], original_query: str, explicit_language: Optional[str] = None) -> QueryAnalysis:
        """Парсинг и валидация результата LLM"""

        try:
            # Нормализация категории
            category = raw_result.get("detected_category")
            if isinstance(category, str):
                category = category.strip()
                if category.lower() == "null" or category == "":
                    category = None
                elif category.lower() in ["indica", "sativa", "hybrid"]:
                    category = category.capitalize()

            # Нормализация THC level
            thc_level = raw_result.get("thc_level")
            if isinstance(thc_level, str):
                thc_level = thc_level.strip().lower()
                if thc_level == "null" or thc_level == "":
                    thc_level = None
                elif thc_level not in ["low", "medium", "high"]:
                    thc_level = None

            # Нормализация CBD level
            cbd_level = raw_result.get("cbd_level")
            if isinstance(cbd_level, str):
                cbd_level = cbd_level.strip().lower()
                if cbd_level == "null" or cbd_level == "":
                    cbd_level = None
                elif cbd_level not in ["low", "medium", "high"]:
                    cbd_level = None

            # Нормализация query intent — default to True if unclear (matches prompt instruction)
            is_search_query = raw_result.get("is_search_query", True)
            if is_search_query is None:
                is_search_query = True
            elif isinstance(is_search_query, str):
                is_search_query = is_search_query.lower() in ["true", "yes", "1"]

            # Нормализация specific strain name
            specific_strain_name = raw_result.get("specific_strain_name")
            if isinstance(specific_strain_name, str):
                specific_strain_name = specific_strain_name.strip()
                if specific_strain_name.lower() in ["null", "", "none"]:
                    specific_strain_name = None

            # Нормализация follow-up
            is_follow_up = raw_result.get("is_follow_up", False)
            if isinstance(is_follow_up, str):
                is_follow_up = is_follow_up.lower() in ["true", "yes", "1"]

            # Parse follow_up_intent (NEW)
            follow_up_intent = None
            raw_intent = raw_result.get("follow_up_intent")
            if raw_intent and isinstance(raw_intent, dict) and is_follow_up:
                try:
                    # Normalize action
                    action = raw_intent.get("action", "describe")
                    if action not in ["compare", "filter", "sort", "select", "describe"]:
                        action = "describe"

                    # Normalize field
                    field = raw_intent.get("field")
                    if field and field not in ["thc", "cbd", "cbg", "category"]:
                        field = "thc"  # Default to THC

                    # Normalize order
                    order = raw_intent.get("order")
                    if order and order not in ["asc", "desc"]:
                        order = "desc"  # Default to highest

                    follow_up_intent = FollowUpIntent(
                        action=action,
                        field=field,
                        order=order,
                        filter_value=raw_intent.get("filter_value"),
                        strain_indices=raw_intent.get("strain_indices")
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse follow_up_intent: {e}")
                    follow_up_intent = None

            # Извлечение атрибутов для post-filtering (as written by user)
            required_flavors = raw_result.get("required_flavors")
            if required_flavors and not isinstance(required_flavors, list):
                required_flavors = None

            required_effects = raw_result.get("required_effects")
            if required_effects and not isinstance(required_effects, list):
                required_effects = None

            required_helps_with = raw_result.get("required_helps_with")
            if required_helps_with and not isinstance(required_helps_with, list):
                required_helps_with = None

            exclude_negatives = raw_result.get("exclude_negatives")
            if exclude_negatives and not isinstance(exclude_negatives, list):
                exclude_negatives = None

            required_terpenes = raw_result.get("required_terpenes")
            if required_terpenes and not isinstance(required_terpenes, list):
                required_terpenes = None

            # Use explicit language if provided, otherwise fallback to LLM result, then default to 'es'
            final_language = explicit_language or raw_result.get("detected_language", "es")

            analysis = QueryAnalysis(
                detected_category=category,
                thc_level=thc_level,
                cbd_level=cbd_level,
                is_search_query=is_search_query,
                specific_strain_name=specific_strain_name,
                is_follow_up=is_follow_up,
                follow_up_intent=follow_up_intent,
                required_flavors=required_flavors,
                required_effects=required_effects,
                required_helps_with=required_helps_with,
                exclude_negatives=exclude_negatives,
                required_terpenes=required_terpenes,
                natural_response=raw_result.get("natural_response", "I can help you find the right strain."),
                suggested_follow_ups=raw_result.get("suggested_follow_ups", []),
                detected_language=final_language,
                confidence=raw_result.get("confidence", 0.9)
            )

            return analysis

        except Exception as e:
            logger.error(f"Error parsing LLM result: {e}")
            raise

    def _fallback_analysis(self, user_query: str, explicit_language: Optional[str] = None) -> QueryAnalysis:
        """Fallback анализ если LLM не работает"""

        query_lower = user_query.lower()

        # Детекция категории
        category = None
        if "indica" in query_lower:
            category = "Indica"
        elif "sativa" in query_lower:
            category = "Sativa"
        elif "hybrid" in query_lower or "híbrido" in query_lower:
            category = "Hybrid"

        # Детекция THC level
        thc_level = None
        if any(word in query_lower for word in ["low thc", "bajo thc", "mild", "suave", "beginners", "principiantes"]):
            thc_level = "low"
        elif any(word in query_lower for word in ["medium thc", "medio thc", "moderate", "moderado"]):
            thc_level = "medium"
        elif any(word in query_lower for word in ["high thc", "alto thc", "strong", "fuerte", "potent", "potente"]):
            thc_level = "high"

        # Детекция CBD level
        cbd_level = None
        if any(word in query_lower for word in ["low cbd", "bajo cbd"]):
            cbd_level = "low"
        elif any(word in query_lower for word in ["medium cbd", "medio cbd"]):
            cbd_level = "medium"
        elif any(word in query_lower for word in ["high cbd", "alto cbd", "medical", "medicinal"]):
            cbd_level = "high"

        # Use explicit language or default to Spanish
        final_language = explicit_language or "es"

        return QueryAnalysis(
            detected_category=category,
            thc_level=thc_level,
            cbd_level=cbd_level,
            is_search_query=True,  # Default to search query in fallback
            natural_response="Puedo ayudarte a encontrar el sorta perfecto. ¿Podrías darme más detalles sobre lo que buscas?",
            suggested_follow_ups=["¿Prefieres indica, sativa o híbrido?", "¿Para qué momento del día?", "¿Algún efecto específico?"],
            detected_language=final_language,
            confidence=0.5
        )

    def _build_fallback_db_context(self) -> str:
        """
        Build minimal hardcoded DB context when ContextBuilder is not available.

        Returns:
            Formatted DB context section (minimal, no user context — that goes in user prompt)
        """
        return """DATABASE CONTEXT (limited - ContextBuilder not available):
Available Flavors: tropical, citrus, earthy, pine, sweet, berry, diesel, cheese, vanilla, menthol, peppermint, lemon, lime
Available Feelings: relaxed, sleepy, happy, euphoric, energetic, focused, creative, uplifted, hungry, talkative
Available Medical Uses: pain, anxiety, stress, insomnia, depression, inflammation, nausea, headaches
Available Negatives: dry mouth, dry eyes, paranoia, anxiety, dizzy, headache
Available Terpenes: Myrcene, Limonene, Pinene, Caryophyllene, Linalool, Humulene
THC Range in DB: 0.5-28.0%
CBD Range in DB: 0.1-15.0%
Categories: Indica, Sativa, Hybrid
"""
