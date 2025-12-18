"""
Streamlined Query Analyzer - Упрощённая версия для векторного поиска

Основная задача:
1. Определить категорию сорта (Indica/Sativa/Hybrid) если упомянута
2. Сгенерировать качественный естественный ответ
3. Предложить follow-up действия

Векторный поиск - ОСНОВНОЙ метод поиска. SQL только для категории.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pydantic import BaseModel, Field
from app.core.llm_interface import LLMInterface
import json
import logging

if TYPE_CHECKING:
    from app.core.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


class QueryAnalysis(BaseModel):
    """Результат упрощённого анализа запроса"""
    detected_category: Optional[str] = Field(None, description="Категория сорта: Indica/Sativa/Hybrid или None")
    thc_level: Optional[str] = Field(None, description="Уровень THC: low/medium/high или None")
    cbd_level: Optional[str] = Field(None, description="Уровень CBD: low/medium/high или None")

    # Query intent detection (CRITICAL for avoiding unnecessary searches)
    is_search_query: bool = Field(default=True, description="Whether user is requesting strain search/recommendation")

    # Specific strain query detection (return only 1 strain, not 5 similar)
    specific_strain_name: Optional[str] = Field(None, description="Exact strain name if user asks about specific strain")

    # Follow-up query detection (SIMPLE)
    is_follow_up: bool = Field(default=False, description="Whether this is a follow-up query referencing previous results")

    # Exact attribute extraction for SQL pre-filtering (PostgreSQL fuzzy matching)
    # Extract as written by user - fuzzy matching handled by PostgreSQL similarity
    required_flavors: Optional[List[str]] = Field(None, description="Flavors mentioned (as written): ['tropical', 'citrus']")
    required_effects: Optional[List[str]] = Field(None, description="Effects mentioned (as written): ['relaxed', 'sleepy']")
    required_helps_with: Optional[List[str]] = Field(None, description="Medical uses (as written): ['pain', 'anxiety']")
    exclude_negatives: Optional[List[str]] = Field(None, description="Side effects to avoid (as written): ['paranoia', 'anxiety']")
    required_terpenes: Optional[List[str]] = Field(None, description="Terpenes mentioned (as written): ['myrcene', 'limonene']")

    natural_response: str = Field(..., description="Естественный ответ пользователю")
    suggested_follow_ups: List[str] = Field(default_factory=list, description="Предлагаемые follow-up действия")
    detected_language: str = Field(default="es", description="Обнаруженный язык (es|en)")
    confidence: float = Field(default=0.9, description="Уверенность в анализе (0.0-1.0)")


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
            context = self._build_context(user_query, session_context, found_strains, fallback_used)

            # Анализ через LLM
            raw_result = self._analyze_with_llm(context, explicit_language)

            # Парсинг результата
            analysis = self._parse_result(raw_result, user_query, explicit_language)

            logger.info(f"Analysis completed: category={analysis.detected_category}, language={analysis.detected_language}")
            return analysis

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return self._fallback_analysis(user_query, explicit_language)

    def _build_context(
        self,
        user_query: str,
        session_context: Optional[Dict[str, Any]],
        found_strains: Optional[List[Dict[str, Any]]],
        fallback_used: bool = False
    ) -> Dict[str, Any]:
        """Построение минимального контекста для LLM"""

        # Базовый контекст
        context = {
            "user_query": user_query,
            "has_session": session_context is not None and len(session_context.get("conversation_history", [])) > 0,
            "conversation_summary": "",
            "previous_language": "es",
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
                context["previous_language"] = session_context.get("detected_language", "es")

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

    def _analyze_with_llm(self, context: Dict[str, Any], explicit_language: Optional[str] = None) -> Dict[str, Any]:
        """Анализ через LLM с динамическим DB контекстом"""

        # Build DB context if ContextBuilder available
        db_context_section = ""
        if self.context_builder:
            try:
                # Get DB taxonomy data
                llm_context = self.context_builder.build_llm_context(
                    user_query=context["user_query"],
                    language=context.get("previous_language", "es"),
                    session_context=None,  # Already in context
                    found_strains=None,
                    fallback_used=bool(context.get("fallback_note"))
                )
                # Build formatted DB context section
                db_context_section = self.context_builder.build_prompt_section(llm_context)
                logger.debug("Using dynamic DB taxonomy context from ContextBuilder")
            except Exception as e:
                logger.warning(f"Failed to build DB context: {e}. Using fallback.")
                db_context_section = self._build_fallback_db_context()
        else:
            logger.debug("ContextBuilder not available - using hardcoded taxonomy")
            db_context_section = self._build_fallback_db_context()

        prompt = """You are an expert cannabis budtender AI assistant.

{db_context}

USER CONTEXT:
User query: "{user_query}"
Previous language: {previous_language}
Conversation summary: {conversation_summary}
Recommended strains: {recommended_strains}
{fallback_note}

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
   - Both EN/ES accepted: "relajado" and "relaxed" both OK
   - DB context contains ALL available values - use it as reference!

5. **Follow-up Query Detection** (CRITICAL LOGIC - analyze carefully):

   **is_follow_up = TRUE** only if ALL conditions met:
   ✓ Previous strains exist in "Recommended strains"
   ✓ User operates on EXISTING results (sort/filter/compare/select operations)
   ✓ NO new search criteria introduced
   ✓ Query references the same context as previous query

   **is_follow_up = FALSE** if ANY of these:
   ✗ User introduces NEW search criteria:
     - Different category than previous (Indica→Sativa, Sativa→Hybrid, etc.)
     - New effects requested (energy, sleep, creativity, etc.)
     - New flavors/taste (tropical, citrus, earthy, etc.)
     - New medical use (pain, anxiety, insomnia, etc.)
     - New THC/CBD level different from previous
   ✗ User requests NEW recommendations (suggest/find/show/recommend)
   ✗ Requirements changed from previous query

   **Examples:**
   - Previous: "show sativa high thc", Current: "which one has lowest thc" → TRUE (sorting same results)
   - Previous: "recommend indica", Current: "the strongest one" → TRUE (selecting from same list)
   - Previous: "show sativa", Current: "and suggest indica with tropical flavor" → FALSE (NEW: category + flavor)
   - Previous: "high thc strains", Current: "also find something for sleep" → FALSE (NEW: medical purpose)
   - Previous: "indica strains", Current: "and recommend sativa for energy" → FALSE (NEW: category + effect)

   **CRITICAL FOR FOLLOW-UP**: If is_follow_up=true, you MUST answer based ONLY on the strains listed in "Recommended strains" above.
   - DO NOT mention strains that are not in the "Recommended strains" list
   - Find the answer by analyzing ONLY the strains provided in the context
   - Example: If "Recommended strains" = [Afghan Kush (15% THC), Hindu Kush (19% THC)], and query is "which has less thc", answer must be "Afghan Kush has the lowest THC at 15%"

5. **Natural Response**:
   - Generate helpful, friendly response in the detected language
   - If strains are recommended, explain WHY they fit the request
   - Mention 1-2 specific strains by name with brief explanation
   - Keep response concise (2-3 sentences)
   - Be conversational like a knowledgeable budtender

6. **Follow-up Suggestions**:
   - Suggest 2-3 relevant follow-up questions
   - Make them contextual to the user's query
   - Use appropriate language for responses

CRITICAL GUIDELINES:
- Category is ONLY for pre-filtering - don't over-specify
- Vector search handles ALL relevance matching
- Focus on high-quality natural response
- Keep it simple and helpful
- **FOLLOW-UP DETECTION IS CRITICAL**: If user references previous results, set is_follow_up=true

⚠️ **ABSOLUTELY CRITICAL FOR FOLLOW-UP QUERIES**:
When is_follow_up=true, you MUST follow these rules for "natural_response":

1. **If query is about comparing/selecting from current list** (e.g., "which has lowest THC", "which is strongest", "show me the indica from that list"):
   - ONLY use strains from "Recommended strains" list above
   - DO NOT mention ANY strains outside this list
   - Example: "Recommended strains" = [A (16% THC), B (19% THC)] + Query "which has lowest THC" → Answer: "A has the lowest THC at 16%"

2. **If current list has NO suitable options for the request** (e.g., user asks for Indica but list only has Sativa):
   - Set is_follow_up=false to trigger new search
   - Explain that current list doesn't match and suggest new search
   - Example: "Recommended strains" = [Sativa1, Sativa2] + Query "show me indica" → is_follow_up=false, suggest new Indica search

3. **NEVER mention strains from general database knowledge when is_follow_up=true and suitable options exist in "Recommended strains"**

RESPONSE FORMAT (JSON only):
{{
  "is_search_query": true|false,
  "specific_strain_name": "Strain Name|null",
  "detected_category": "Indica|Sativa|Hybrid|null",
  "thc_level": "low|medium|high|null",
  "cbd_level": "low|medium|high|null",
  "is_follow_up": true|false,
  "required_flavors": ["flavor1", "flavor2"] or null,
  "required_effects": ["effect1", "effect2"] or null,
  "required_helps_with": ["condition1", "condition2"] or null,
  "exclude_negatives": ["negative1", "negative2"] or null,
  "required_terpenes": ["terpene1", "terpene2"] or null,
  "natural_response": "Response mentioning specific strains (answer based on previous strains if is_follow_up=true)",
  "suggested_follow_ups": ["follow-up 1", "follow-up 2", "follow-up 3"],
  "confidence": 0.0-1.0
}}

EXAMPLES:

--- NON-SEARCH QUERIES (is_search_query = FALSE) ---

Query: "hey, how can you help me"
{{
  "is_search_query": false,
  "specific_strain_name": null,
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "¡Hola! I'm your cannabis budtender. I can help you find the perfect strain based on your needs - whether you're looking for relaxation, energy, pain relief, or specific flavors. What would you like to know?",
  "suggested_follow_ups": ["Show me relaxing strains", "I need something for sleep", "What's good for pain relief?"],
  "confidence": 0.95
}}

Query: "hola, ¿qué puedes hacer?"
{{
  "is_search_query": false,
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "¡Hola! Puedo ayudarte a encontrar la cepa perfecta según tus necesidades - ya sea relajación, energía, alivio del dolor, o sabores específicos. ¿Qué buscas?",
  "suggested_follow_ups": ["Muéstrame cepas relajantes", "Necesito algo para dormir", "¿Qué es bueno para el dolor?"],
  "confidence": 0.95
}}

Query: "thank you!"
{{
  "is_search_query": false,
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "You're welcome! Feel free to ask if you need anything else. I'm here to help you find the perfect strain!",
  "suggested_follow_ups": ["Show me popular strains", "I need something energizing", "Help with anxiety"],
  "confidence": 0.95
}}

--- SEARCH QUERIES (is_search_query = TRUE) ---

Query: "necesito algo para dormir mejor"
{{
  "is_search_query": true,
  "detected_category": "Indica",
  "thc_level": null,
  "cbd_level": null,
  "natural_response": "Te recomendaría Northern Lights, una indica clásica perfecta para dormir. Su alto contenido de THC y efectos relajantes te ayudarán a conciliar el sueño profundamente.",
  "suggested_follow_ups": ["¿Prefieres algo con más CBD?", "¿Necesitas algo que no cause somnolencia matutina?", "¿Te interesan otras indicas similares?"],
  "confidence": 0.95
}}

Query: "show me high THC strains"
{{
  "is_search_query": true,
  "detected_category": null,
  "thc_level": "high",
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "I found several high-THC strains for you. GMO Cookies (28% THC) and Kush Mints (28% THC) are excellent choices with potent effects.",
  "suggested_follow_ups": ["Would you like sativa or indica?", "Any specific effects you're looking for?", "Do you prefer a particular flavor profile?"],
  "confidence": 0.9
}}

Query: "suggest me sativa strains with low thc"
{{
  "detected_category": "Sativa",
  "thc_level": "low",
  "cbd_level": null,
  "natural_response": "For a mild sativa, I recommend Harlequin (5% THC). It provides gentle energy and focus without overwhelming psychoactive effects, perfect for beginners.",
  "suggested_follow_ups": ["Would you like higher CBD for medical benefits?", "Any specific effects you're looking for?", "Do you prefer citrus or earthy flavors?"],
  "confidence": 0.95
}}

Query: "dame algo energético para trabajar"
{{
  "detected_category": "Sativa",
  "thc_level": null,
  "cbd_level": null,
  "natural_response": "Para trabajar te recomiendo Green Crack, una sativa energizante que mejora el foco y la creatividad sin causar ansiedad. Perfecto para uso diurno productivo.",
  "suggested_follow_ups": ["¿Prefieres algo con menos THC?", "¿Necesitas algo que también ayude con creatividad?", "¿Te interesan híbridos con efecto similar?"],
  "confidence": 0.95
}}

Query: "which strains help with pain?"
{{
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": ["pain"],
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "For pain relief, I recommend Blue Dream and ACDC. Blue Dream offers balanced effects with moderate THC, while ACDC is high in CBD for medical benefits without strong psychoactive effects.",
  "suggested_follow_ups": ["Do you prefer indica or sativa?", "Would you like high-CBD options?", "Any specific type of pain?"],
  "confidence": 0.9
}}

Query: "suggest me indica with tropical flavor and high thc"
{{
  "detected_category": "Indica",
  "thc_level": "high",
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": ["tropical"],
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "I'll find you an indica with tropical flavors and high THC. Watermelon Zkittlez (24% THC) offers sweet tropical notes with strong relaxing effects, perfect for evening use.",
  "suggested_follow_ups": ["Would you like something sweeter?", "Do you need help with sleep?", "Any specific effects you're looking for?"],
  "confidence": 0.95
}}

--- SPECIFIC STRAIN QUERIES (return only 1 strain, not 5 similar) ---

Query: "do you have info about Tropicana Cookies?"
{{
  "is_search_query": true,
  "specific_strain_name": "Tropicana Cookies",
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "Tropicana Cookies is a sativa strain with 16% THC. It's known for energizing and creative effects with a tropical, citrus flavor profile - perfect for daytime use.",
  "suggested_follow_ups": ["Would you like similar sativa strains?", "Any other strain you'd like to know about?", "Looking for something for a specific purpose?"],
  "confidence": 0.95
}}

Query: "cuéntame sobre ACDC"
{{
  "is_search_query": true,
  "specific_strain_name": "ACDC",
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": false,
  "required_flavors": null,
  "required_effects": null,
  "required_helps_with": null,
  "exclude_negatives": null,
  "required_terpenes": null,
  "natural_response": "ACDC es una cepa híbrida con muy bajo THC (1%) y alto CBD (14%). Es ideal para beneficios medicinales sin efectos psicoactivos fuertes, excelente para dolor y estrés.",
  "suggested_follow_ups": ["¿Quieres otras cepas con alto CBD?", "¿Buscas algo para alguna condición específica?", "¿Te interesan cepas similares?"],
  "confidence": 0.95
}}

--- FOLLOW-UP QUERY EXAMPLES (CRITICAL) ---

Context: Previous strains shown: Animal Cookies (19% THC), Animal Mints (16% THC), GMO Cookies (28% THC)
Query: "which one has less thc" (or "cual tiene menos thc")
{{
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": true,
  "natural_response": "Animal Mints has the lowest THC at 16%, followed by Animal Cookies at 19%.",
  "suggested_follow_ups": ["Tell me about Animal Mints effects", "Do you have something even milder?", "Compare Animal Mints and Animal Cookies"],
  "confidence": 0.95
}}

Context: Previous strains shown: G13 (Indica, 20% THC), Truffle (Hybrid, 24% THC), Kush Mints (Hybrid, 28% THC)
Query: "and suggest me indica with tropical flavor and high thc"
{{
  "detected_category": "Indica",
  "thc_level": "high",
  "cbd_level": null,
  "is_follow_up": false,
  "natural_response": "Te recomiendo buscar indicas con sabores tropicales y alto THC. Aunque la combinación exacta puede ser rara, puedo buscar opciones similares.",
  "suggested_follow_ups": ["¿Prefieres algo con sabor cítrico?", "¿Te interesan híbridos tropicales?", "¿Qué nivel de THC buscas exactamente?"],
  "confidence": 0.85
}}

Context: Previous strains shown: Blue Dream (18% THC), ACDC (1% THC), Northern Lights (21% THC)
Query: "cual es el más potente" (or "which is the strongest")
{{
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": true,
  "natural_response": "De esos, Northern Lights es el más potente con 21% de THC.",
  "suggested_follow_ups": ["¿Cuáles son los efectos?", "¿Necesitas algo más fuerte?", "¿Comparar con Blue Dream?"],
  "confidence": 0.95
}}

Context: Previous strains shown: Green Crack (Sativa), Blue Dream (Hybrid), Durban Poison (Sativa)
Query: "show me only the hybrids from that list" (or "solo los híbridos de esa lista")
{{
  "detected_category": null,
  "thc_level": null,
  "cbd_level": null,
  "is_follow_up": true,
  "natural_response": "From the previous list, only Blue Dream is a hybrid. It offers balanced effects between relaxation and energy.",
  "suggested_follow_ups": ["Would you like more hybrid options?", "Tell me about Blue Dream effects", "Show me similar hybrids"],
  "confidence": 0.95
}}
"""

        # Merge DB context with user context for formatting
        format_context = {**context, "db_context": db_context_section}
        formatted_prompt = prompt.format(**format_context)

        # Получение JSON ответа от LLM
        try:
            if hasattr(self.llm, 'extract_json'):
                result = self.llm.extract_json(formatted_prompt)
            else:
                response = self.llm.generate_response(formatted_prompt)
                result = self._extract_json_from_response(response)

            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
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

            # Нормализация query intent
            is_search_query = raw_result.get("is_search_query", True)  # Default to True
            if isinstance(is_search_query, str):
                is_search_query = is_search_query.lower() in ["true", "yes", "1"]

            # Нормализация specific strain name
            specific_strain_name = raw_result.get("specific_strain_name")
            if isinstance(specific_strain_name, str):
                specific_strain_name = specific_strain_name.strip()
                if specific_strain_name.lower() in ["null", "", "none"]:
                    specific_strain_name = None

            # Нормализация follow-up (simple)
            is_follow_up = raw_result.get("is_follow_up", False)
            if isinstance(is_follow_up, str):
                is_follow_up = is_follow_up.lower() in ["true", "yes", "1"]

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
        Build minimal hardcoded DB context when ContextBuilder is not available

        Returns:
            Formatted DB context section (minimal)
        """
        return """DATABASE CONTEXT (limited - ContextBuilder not available):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Available Flavors: tropical, citrus, earthy, pine, sweet, berry, diesel, cheese, vanilla, menthol, peppermint, lemon, lime
Available Feelings: relaxed, sleepy, happy, euphoric, energetic, focused, creative, uplifted, hungry, talkative
Available Medical Uses: pain, anxiety, stress, insomnia, depression, inflammation, nausea, headaches
Available Negatives: dry mouth, dry eyes, paranoia, anxiety, dizzy, headache
Available Terpenes: Myrcene, Limonene, Pinene, Caryophyllene, Linalool, Humulene

THC Range in DB: 0.5-28.0%
CBD Range in DB: 0.1-15.0%
Categories: Indica, Sativa, Hybrid
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NOTE: Using hardcoded taxonomy. For complete DB data, integrate ContextBuilder.
"""
