from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field  # type: ignore[import-not-found]
from app.models.session import ConversationSession
from app.models.schemas import Strain
from app.core.llm_interface import LLMInterface
import json
import logging

logger = logging.getLogger(__name__)


class ActionPlan(BaseModel):
    """План выполнения действия от AI"""
    primary_action: str = Field(..., description="Основное действие: sort_strains|filter_strains|select_strains|explain_strains|expand_search")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Параметры для выполнения действия")
    reasoning: str = Field(..., description="Объяснение почему выбрано это действие")


class SmartAnalysis(BaseModel):
    """Результат умного анализа запроса"""
    action_plan: ActionPlan = Field(..., description="План выполнения")
    natural_response: str = Field(..., description="Естественный ответ пользователю")
    suggested_follow_ups: List[str] = Field(default_factory=list, description="Предлагаемые follow-up действия")
    confidence: float = Field(..., description="Уверенность в анализе (0.0-1.0)")
    detected_language: str = Field(..., description="Обнаруженный язык (es|en)")
    is_fallback: bool = Field(default=False, description="Флаг fallback анализа")


class SmartQueryAnalyzer:
    """
    Smart Query Analyzer v3.0
    Главный AI компонент для анализа пользовательских запросов с полным контекстом
    """
    
    def __init__(self, llm_interface: LLMInterface):
        self.llm = llm_interface
        self.available_actions = [
            "search_strains",    # Поиск новых сортов из БД по критериям
            "sort_strains",      # Сортировка сортов по критериям
            "filter_strains",    # Фильтрация сортов по условиям
            "select_strains",    # Выбор конкретных сортов (по индексу, имени)
            "explain_strains",   # Объяснение характеристик сортов
            "expand_search"      # Расширение поиска новыми сортами
        ]
    
    def analyze_query(
        self,
        user_query: str,
        session: ConversationSession,
        session_strains: List[Strain],
        full_context: Optional[Dict[str, Any]] = None,
        policy_hint: Optional[Dict[str, Any]] = None
    ) -> SmartAnalysis:
        """
        Главный метод анализа запроса с полным контекстом
        """
        logger.info(f"Smart analysis starting for query: {user_query[:50]}...")
        
        try:
            # Нормализуем контекст в нужный формат
            if full_context:
                # Адаптируем контекст от ContextProvider к нашему формату
                context = self._adapt_external_context(full_context, user_query, session, session_strains)
            else:
                # Строим свой контекст
                context = self._build_full_context(user_query, session, session_strains)
            
            # Подсказки политики диалога (если есть)
            if policy_hint:
                context["policy_hint"] = policy_hint
            else:
                context["policy_hint"] = {}
            
            # Анализ через LLM
            raw_result = self._analyze_with_llm(context)
            
            # Парсинг и валидация результата
            analysis = self._parse_llm_result(raw_result, user_query)
            
            logger.info(f"Smart analysis completed: {analysis.action_plan.primary_action}, confidence: {analysis.confidence}")
            return analysis
            
        except Exception as e:
            logger.warning(f"Smart analysis failed, using fallback: {e}")
            return self._fallback_analysis(user_query, session, session_strains)
    
    def _build_full_context(
        self,
        user_query: str,
        session: ConversationSession,
        session_strains: List[Strain]
    ) -> Dict[str, Any]:
        """Построение полного контекста для AI анализа"""
        
        # Подробная информация о сортах в сессии
        strains_context = []
        for strain in session_strains:
            strain_info = {
                "id": strain.id,
                "name": strain.name,
                "category": strain.category,
                "thc": strain.thc,
                "cbd": strain.cbd,
                "cbg": strain.cbg,
                "effects": [f.name for f in strain.feelings] if strain.feelings else [],
                "helps_with": [h.name for h in strain.helps_with] if strain.helps_with else [],
                "negatives": [n.name for n in strain.negatives] if strain.negatives else [],
                "flavors": [fl.name for fl in strain.flavors] if strain.flavors else []
            }
            strains_context.append(strain_info)
        
        # Контекст разговора
        conversation_summary = ""
        if session.conversation_history:
            recent_entries = session.conversation_history[-3:]  # Последние 3 сообщения
            conversation_summary = " | ".join([
                f"User: {entry.get('query', '')[:50]}... AI: {entry.get('response', '')[:50]}..."
                for entry in recent_entries
            ])
        
        return {
            "user_query": user_query,
            "session_strains": strains_context,
            "conversation_context": conversation_summary,
            "user_preferences": {
                k: list(v) if isinstance(v, set) else v 
                for k, v in session.user_preferences.items()
            },
            "current_topic": session.current_topic.value if session.current_topic else None,
            "detected_language": session.detected_language,
            "available_actions": self.available_actions,
            "has_session_context": len(strains_context) > 0
        }
    
    def _adapt_external_context(
        self,
        external_context: Dict[str, Any],
        user_query: str,
        session: ConversationSession,
        session_strains: List[Strain]
    ) -> Dict[str, Any]:
        """Адаптация внешнего контекста к формату SmartQueryAnalyzer"""
        
        session_metadata = external_context.get("session_metadata", {})
        context_summary = external_context.get("context_summary", {})
        
        return {
            "user_query": user_query,
            "session_strains": external_context.get("session_strains", []),
            "conversation_context": external_context.get("conversation_context", ""),
            "user_preferences": external_context.get("user_preferences", {}),
            "current_topic": session_metadata.get("current_topic"),
            "detected_language": session_metadata.get("detected_language"),
            "available_actions": self.available_actions,
            "has_session_context": context_summary.get("has_strains", False)
        }
    
    def _analyze_with_llm(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Анализ через LLM с unified prompt"""
        
        prompt = """
You are a cannabis strain consultation AI analyzing user queries with full session context.

CONTEXT:
User query: "{user_query}"
Session strains: {session_strains}
Conversation history: {conversation_context}
User preferences: {user_preferences}
Current topic: {current_topic}
Previous language: {detected_language}
Available system actions: {available_actions}
Has session context: {has_session_context}
Policy hint (may be empty): {policy_hint}

TASK:
Analyze the user's query and create a smart execution plan. Consider:

1. What does the user want to accomplish?
2. Which strains from the session are relevant?
3. How should the data be processed (filter/sort/select/explain)?
4. What data quality issues need handling (null/N/A/invalid values)?
5. What would be most helpful and natural for the user?

CRITICAL GUIDELINES:
- **MEDICAL-FIRST PRIORITY**: When user mentions medical conditions (insomnia, anxiety, pain, depression, etc.), prioritize medical relevance over other criteria
- **CONTRADICTION DETECTION**: Automatically exclude contradictory effects:
  * insomnia/sleep queries → exclude "Energetic", "Uplifted", "Creative" effects
  * anxiety queries → exclude "Paranoid", "Anxious" negative effects  
  * depression queries → INCLUDE "Uplifted", "Creative", "Happy" effects (beneficial for mood)
  * energy queries → exclude "Sleepy", "Relaxed", "Couch Lock" effects
- **MULTI-STAGE FILTERING**: Use priority system (1=highest, 3=lowest):
  * Medical conditions (helps_with) → priority: 1
  * Effect compatibility → priority: 1  
  * Secondary criteria (THC, CBD, category) → priority: 2
  * Tertiary criteria (flavors, appearance) → priority: 3
- **SMART SCORING**: Use multi-criteria scoring instead of simple filtering
- Always exclude strains with null/N/A/invalid data when not useful for the query
- Provide natural language response in the detected language. If uncertain, prefer English.
- Respect policy hints when reasonable: if user requests a different category/effects/flavors that don't match session strains, prefer "search_strains" or "expand_search" with appropriate filters and optional THC sort.

RESPONSE FORMAT (JSON only, no additional text):
{{
  "action_plan": {{
    "primary_action": "sort_strains|filter_strains|select_strains|explain_strains|search_strains",
    "parameters": {{
      "filters": {{
        "helps_with": {{"operator": "contains", "values": ["Insomnia"], "priority": 1}},
        "effects": {{"operator": "not_contains", "values": ["Energetic", "Uplifted", "Creative"], "priority": 1}},
        "thc": {{"operator": "gte", "value": 15, "priority": 2}},
        "category": {{"operator": "eq", "value": "Indica", "priority": 2}}
      }},
      "scoring": {{
        "method": "weighted_priority|simple_sort",
        "primary_field": "medical_relevance|thc|cbd",
        "secondary_field": "thc|cbd|category"
      }},
      "sort": {{"field": "score|thc|cbd|cbg|name|category", "order": "asc|desc"}},
      "selection": {{"index": 0, "name": "strain_name", "id": 0}},
      "exclude_invalid": ["null", "N/A", "unknown"],
      "limit": 5,
      "reasoning": "detailed explanation including medical priorities and contradictions avoided"
    }}
  }},
  "natural_response": "Natural language response in appropriate language",
  "suggested_follow_ups": ["contextual suggestion 1", "contextual suggestion 2", "contextual suggestion 3"],
  "confidence": 0.0-1.0,
  "detected_language": "es|en"
}}

UNIVERSAL FILTER OPERATORS:
- "eq": exact match (category = "Indica")
- "gte"/">=": greater or equal (thc >= 15)  
- "lte"/"<=": less or equal (cbd <= 5)
- "gt"/">": greater than (thc > 20)
- "lt"/"<": less than (cbg < 2)
- "contains": array contains any of values (effects contains ["Sleepy", "Relaxed"])
- "any": field matches any of values (category any of ["Indica", "Hybrid"])
- "not_contains": array doesn't contain values (effects not_contains ["Energetic"])

SORTING ORDER GUIDELINES:
- **HIGHEST/STRONGEST/MOST** → order: "desc" (descending, high to low)
- **LOWEST/SMALLEST/LEAST/MILDEST** → order: "asc" (ascending, low to high)
- **"from lowest to highest"** → order: "asc"
- **"from highest to lowest"** → order: "desc"

AVAILABLE STRAIN FIELDS:
- Basic: name, category, thc, cbd, cbg, slug
- Arrays: effects/feelings, helps_with/medical, negatives/side_effects, flavors

MEDICAL-PRIORITY EXAMPLES:
- "high thc strains for insomnia" → search_strains with:
  * filters: {{"helps_with": {{"operator": "contains", "values": ["Insomnia"], "priority": 1}}, "effects": {{"operator": "not_contains", "values": ["Energetic", "Uplifted", "Creative"], "priority": 1}}, "thc": {{"operator": "gte", "value": 15, "priority": 2}}}}
  * scoring: {{"method": "weighted_priority", "primary_field": "medical_relevance", "secondary_field": "thc"}}

- "anxiety relief with high CBD" → search_strains with:
  * filters: {{"helps_with": {{"operator": "contains", "values": ["Anxiety"], "priority": 1}}, "negatives": {{"operator": "not_contains", "values": ["Paranoid", "Anxious"], "priority": 1}}, "cbd": {{"operator": "gte", "value": 10, "priority": 2}}}}

- "hybrid strains for depression" → search_strains with:
  * filters: {{"helps_with": {{"operator": "contains", "values": ["Depression", "Stress"], "priority": 1}}, "effects": {{"operator": "contains", "values": ["Uplifted", "Happy"], "priority": 1}}, "category": {{"operator": "eq", "value": "Hybrid", "priority": 2}}}}

- "energizing sativas for creativity" → search_strains with:
  * filters: {{"effects": {{"operator": "contains", "values": ["Creative", "Uplifted"], "priority": 1}}, "effects": {{"operator": "not_contains", "values": ["Sleepy", "Relaxed"], "priority": 1}}, "category": {{"operator": "eq", "value": "Sativa", "priority": 2}}}}

NON-MEDICAL EXAMPLES:
- "what strain have highest thc level" → sort_strains with sort={{"field": "thc", "order": "desc"}}, exclude_invalid=["null", "N/A"]
- "which one has the lowest THC level" → sort_strains with sort={{"field": "thc", "order": "asc"}}, exclude_invalid=["null", "N/A"]
- "show me the one with the smallest THC percentage" → sort_strains with sort={{"field": "thc", "order": "asc"}}, limit=1
- "sort by THC from lowest to highest" → sort_strains with sort={{"field": "thc", "order": "asc"}}
- "show citrus flavored strains" → search_strains with filters={{"flavors": {{"operator": "contains", "values": ["citrus"], "priority": 2}}}}

KEY PRINCIPLES:
- **MEDICAL CONDITIONS = PRIORITY 1**: helps_with field always gets highest priority
- **EFFECT COMPATIBILITY = PRIORITY 1**: Exclude contradictory effects 
- **SECONDARY CRITERIA = PRIORITY 2**: THC, CBD, category
- **TERTIARY CRITERIA = PRIORITY 3**: flavors, appearance
- **SORTING DIRECTION**: "lowest/smallest/mildest" = asc, "highest/strongest/most" = desc
- Use weighted_priority scoring for medical queries, simple_sort for non-medical
"""
        
        formatted_prompt = prompt.format(**context)
        
        # Получение JSON ответа от LLM
        result = self._call_llm_with_json_extraction(formatted_prompt)
        return result
    
    def _call_llm_with_json_extraction(self, prompt: str) -> Dict[str, Any]:
        """Вызов LLM с извлечением JSON"""
        
        # Проверим, есть ли метод extract_json у LLM интерфейса
        if hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(prompt)
        
        # Fallback - обычный вызов и попытка парсинга JSON
        response = self.llm.generate_response(prompt)
        
        # Поиск JSON в ответе
        try:
            # Попытка найти JSON блок в ответе
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in LLM response")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"LLM response: {response}")
            raise
    
    def _parse_llm_result(self, raw_result: Dict[str, Any], original_query: str) -> SmartAnalysis:
        """Парсинг и валидация результата LLM"""
        
        try:
            # Создание ActionPlan
            action_data = raw_result.get("action_plan", {})
            action_plan = ActionPlan(
                primary_action=action_data.get("primary_action", "explain_strains"),
                parameters=action_data.get("parameters", {}),
                reasoning=action_data.get("parameters", {}).get("reasoning", "Default reasoning")
            )
            
            # Создание SmartAnalysis
            analysis = SmartAnalysis(
                action_plan=action_plan,
                natural_response=raw_result.get("natural_response", "I can help you with that."),
                suggested_follow_ups=raw_result.get("suggested_follow_ups", []),
                confidence=raw_result.get("confidence", 0.8),
                detected_language=raw_result.get("detected_language", "en"),
                is_fallback=False
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error parsing LLM result: {e}")
            raise
    
    def _fallback_analysis(
        self,
        user_query: str,
        session: ConversationSession,
        session_strains: List[Strain]
    ) -> SmartAnalysis:
        """Fallback анализ на основе простых правил"""
        
        query_lower = user_query.lower()
        
        # Определение языка
        spanish_indicators = ['cuál', 'qué', 'para', 'necesito', 'quiero', 'más', 'mejor']
        detected_language = 'es' if any(word in query_lower for word in spanish_indicators) else 'en'
        
        # Определение действия по ключевым словам
        action = "explain_strains"  # По умолчанию
        parameters: Dict[str, Any] = {"reasoning": "Fallback rule-based analysis"}
        
        if any(word in query_lower for word in ['highest', 'strongest', 'más', 'fuerte', 'potent']):
            action = "sort_strains"
            parameters.update({
                "sort_by": "thc",
                "sort_order": "desc",
                "exclude_invalid": ["null", "N/A", "unknown"],
                "limit": 3,
                "reasoning": "User wants strongest strains by THC"
            })
        elif any(word in query_lower for word in ['lowest', 'mildest', 'suave', 'débil', 'weak']):
            action = "sort_strains"
            parameters.update({
                "sort_by": "thc", 
                "sort_order": "asc",
                "exclude_invalid": ["null", "N/A", "unknown"],
                "limit": 3,
                "reasoning": "User wants mildest strains by THC"
            })
        elif any(word in query_lower for word in ['indica', 'sativa', 'hybrid']):
            action = "filter_strains"
            category = "Indica" if "indica" in query_lower else "Sativa" if "sativa" in query_lower else "Hybrid"
            parameters.update({
                "criteria": {"category": category},
                "reasoning": f"User wants {category} strains"
            })
        elif len(session_strains) == 0:
            action = "expand_search"
            parameters.update({
                "reasoning": "No session context, need to search for new strains"
            })
        
        # Создание fallback ответа
        responses = {
            'es': "Permíteme ayudarte con eso basándome en las opciones disponibles.",
            'en': "Let me help you with that based on the available options."
        }
        
        action_plan = ActionPlan(
            primary_action=action,
            parameters=parameters,
            reasoning=parameters["reasoning"]
        )
        
        return SmartAnalysis(
            action_plan=action_plan,
            natural_response=responses[detected_language],
            suggested_follow_ups=[],
            confidence=0.5,  # Низкая уверенность для fallback
            detected_language=detected_language,
            is_fallback=True
        )