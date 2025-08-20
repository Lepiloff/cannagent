import json
import logging
from typing import Dict, Any, Optional
from app.models.session import ConversationSession, UnifiedAnalysis
from app.core.llm_interface import get_llm
from app.core.intent_detection import IntentType

logger = logging.getLogger(__name__)


class UnifiedLLMProcessor:
    """Объединяет все LLM операции в один вызов для оптимизации"""
    
    def __init__(self):
        self.llm = get_llm()
        self.timeout = 3000  # 3 секунды timeout
        
    def analyze_complete(
        self, 
        query: str, 
        session: ConversationSession
    ) -> UnifiedAnalysis:
        """ОДИН вызов LLM вместо 4-5"""
        
        # Подготовка контекста
        context_summary = self._build_context_summary(session)
        
        # Формируем единый prompt
        prompt = self._build_unified_prompt(query, session, context_summary)
        
        try:
            # Единый вызов LLM с извлечением JSON
            result = self._call_llm_with_json_extraction(prompt)
            
            # Валидация и создание UnifiedAnalysis
            analysis = self._create_unified_analysis(result, query)
            
            logger.info(f"Unified LLM analysis completed: {analysis.query_type}, confidence: {analysis.confidence}")
            return analysis
            
        except Exception as e:
            logger.warning(f"LLM failed, will use fallback: {e}")
            raise  # Пусть вызывающий код решает как обработать
    
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
    
    def _build_unified_prompt(
        self, 
        query: str, 
        session: ConversationSession, 
        context_summary: Dict[str, Any]
    ) -> str:
        """Построение единого промпта для полного анализа"""
        
        prompt = f"""
        Analyze this cannabis consultation query and return complete analysis in JSON.
        
        Query: {query}
        Language hint: {context_summary.get('last_language', 'es')}
        Has previous recommendations: {context_summary.get('has_strains', False)}
        Last strains: {context_summary.get('last_strains', 'none')}
        Previous topic: {context_summary.get('previous_topic', 'none')}
        User preferences accumulated: {context_summary.get('preferences', {})}
        
        Return JSON with ALL of the following:
        {{
            "detected_language": "es|en",
            "query_type": "new_search|follow_up|comparison|detail_request|reset|clarification",
            "confidence": 0.0-1.0,
            "topic_changed": true|false,
            "criteria": {{
                "potency": {{"thc": "higher|lower|specific", "value": null}},
                "effects": {{"desired": [], "avoid": [], "priority": ""}},
                "medical_conditions": [],
                "flavors": {{"preferred": [], "avoid": []}},
                "strain_reference": {{"type": "index|name|all", "value": ""}},
                "custom_criteria": "",
                "conflicts_detected": []
            }},
            "action_needed": "filter|sort|compare|select|explain|clarify",
            "suggested_quick_actions": ["dynamic suggestions based on context"],
            "response_text": "Generated natural response in detected language"
        }}
        
        Critical instructions:
        - Detect if this is about previously mentioned strains (follow_up)
        - Check for conflicting criteria (e.g., "sleepy but energetic")
        - Generate response text in the detected language
        - Suggest relevant quick actions based on the context
        - For follow_up queries, reference should be "index" (like "first", "mejor") or "name" (specific strain name)
        - For reset queries ("empezar de nuevo", "start over"), set query_type to "reset"
        - Spanish examples: "necesito dormir" -> new_search, "¿cuál es mejor?" -> follow_up, "empezar de nuevo" -> reset
        - English examples: "need energy" -> new_search, "which is stronger?" -> follow_up, "start over" -> reset
        """
        
        return prompt
    
    def _build_context_summary(self, session: ConversationSession) -> Dict[str, Any]:
        """Построение краткого контекста для LLM"""
        
        summary = {
            'last_language': session.detected_language or 'es',
            'has_strains': session.has_strains(),
            'last_strains': 'none',
            'previous_topic': 'none',
            'preferences': {}
        }
        
        # Последние рекомендованные сорта
        if session.has_strains():
            last_strain_ids = session.get_last_strains()
            summary['last_strains'] = f"{len(last_strain_ids)} strains (IDs: {last_strain_ids[:3]}{'...' if len(last_strain_ids) > 3 else ''})"
        
        # Предыдущая тема
        if session.current_topic:
            summary['previous_topic'] = session.current_topic.value
        
        # Краткие предпочтения
        if session.user_preferences:
            summary['preferences'] = {
                k: list(v)[:5] if isinstance(v, set) else v  # Ограничиваем количество для контекста
                for k, v in list(session.user_preferences.items())[:3]  # Максимум 3 категории
            }
        
        return summary
    
    def _create_unified_analysis(self, llm_result: Dict[str, Any], original_query: str) -> UnifiedAnalysis:
        """Создание объекта UnifiedAnalysis из результата LLM"""
        
        try:
            # Валидация обязательных полей
            required_fields = ['detected_language', 'query_type', 'confidence', 'action_needed', 'response_text']
            for field in required_fields:
                if field not in llm_result:
                    raise ValueError(f"Missing required field: {field}")
            
            # Создание объекта с валидацией типов
            analysis = UnifiedAnalysis(
                detected_language=llm_result['detected_language'],
                query_type=llm_result['query_type'],
                confidence=float(llm_result['confidence']),
                topic_changed=llm_result.get('topic_changed', False),
                criteria=llm_result.get('criteria'),
                action_needed=llm_result['action_needed'],
                suggested_quick_actions=llm_result.get('suggested_quick_actions', []),
                response_text=llm_result['response_text'],
                original_query=original_query,
                is_fallback=False
            )
            
            # Проверка конфликтов в критериях
            if analysis.criteria and analysis.criteria.get('conflicts_detected'):
                analysis.warnings = analysis.criteria['conflicts_detected']
            
            return analysis
            
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error creating UnifiedAnalysis from LLM result: {e}")
            logger.debug(f"LLM result: {llm_result}")
            
            # Fallback создание с минимальными данными
            return UnifiedAnalysis(
                detected_language=llm_result.get('detected_language', 'es'),
                query_type=llm_result.get('query_type', 'clarification'),
                confidence=0.3,  # Низкая уверенность при ошибках парсинга
                action_needed='clarify',
                response_text=llm_result.get('response_text', 'Lo siento, no pude entender completamente tu pregunta.'),
                original_query=original_query,
                is_fallback=True,
                warnings=[f"LLM parsing error: {str(e)}"]
            )