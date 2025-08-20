import logging
from typing import Dict, Any, List, Optional
from app.models.session import ConversationSession, UnifiedAnalysis
from app.core.intent_detection import IntentType

logger = logging.getLogger(__name__)


class RuleBasedFallbackAnalyzer:
    """Резервный анализатор когда LLM недоступен"""
    
    def __init__(self):
        # Словари для детекции языка
        self.spanish_keywords = [
            'necesito', 'quiero', 'cuál', 'para', 'me', 'mi', 'dolor', 'dormir', 
            'energía', 'creatividad', 'relajar', 'fuerte', 'suave', 'mejor',
            'primera', 'último', 'estos', 'esas', 'más', 'menos', 'nuevo',
            'empezar', 'comenzar', 'de', 'nuevo', 'otra', 'vez'
        ]
        
        self.english_keywords = [
            'need', 'want', 'which', 'what', 'for', 'pain', 'sleep', 'energy',
            'creativity', 'relax', 'strong', 'mild', 'better', 'best', 'first',
            'last', 'these', 'those', 'more', 'less', 'new', 'start', 'over',
            'again', 'another'
        ]
        
        # Паттерны для типов запросов
        self.reset_patterns = [
            'empezar de nuevo', 'empezar nuevo', 'nueva consulta', 'nuevo',
            'start over', 'start new', 'new search', 'reset', 'restart'
        ]
        
        self.follow_up_patterns = [
            'cuál', 'which', 'mejor', 'better', 'best', 'primero', 'first', 
            'último', 'last', 'estos', 'these', 'esos', 'those', 'más fuerte',
            'stronger', 'más suave', 'milder', 'compare', 'comparar'
        ]
        
        # Эффекты и их категории
        self.effect_keywords = {
            'sleep': ['dormir', 'sueño', 'insomnio', 'sleep', 'sleepy', 'insomnia'],
            'energy': ['energía', 'activo', 'despertar', 'energy', 'energetic', 'active'],
            'pain': ['dolor', 'dolores', 'pain', 'aches', 'chronic'],
            'creativity': ['creatividad', 'creativo', 'inspiración', 'creativity', 'creative', 'inspiration'],
            'relaxation': ['relajar', 'relajado', 'tranquilo', 'relax', 'relaxed', 'calm'],
            'focus': ['concentración', 'enfoque', 'focus', 'focused', 'concentration']
        }
        
        # Потенциальность
        self.potency_keywords = {
            'higher': ['fuerte', 'potente', 'más', 'strong', 'potent', 'high', 'higher'],
            'lower': ['suave', 'ligero', 'menos', 'mild', 'light', 'low', 'lower']
        }
    
    def analyze(self, query: str, session: ConversationSession) -> UnifiedAnalysis:
        """Простой rule-based анализ без LLM"""
        
        query_lower = query.lower()
        
        # 1. Детекция языка по ключевым словам
        language = self._detect_language(query_lower)
        
        # 2. Определение типа запроса
        query_type = self._detect_query_type(query_lower, session)
        
        # 3. Извлечение базовых критериев
        criteria = self._extract_criteria(query_lower)
        
        # 4. Определение действия
        action_needed = self._determine_action(query_type, criteria)
        
        # 5. Простой ответ
        response_text = self._generate_response(query_type, language, criteria)
        
        # 6. Quick actions
        quick_actions = self._generate_quick_actions(query_type, language, session)
        
        return UnifiedAnalysis(
            detected_language=language,
            query_type=query_type,
            confidence=0.5,  # Низкая уверенность для fallback
            topic_changed=self._detect_topic_change(criteria, session),
            criteria=criteria,
            action_needed=action_needed,
            suggested_quick_actions=quick_actions,
            response_text=response_text,
            original_query=query,
            is_fallback=True
        )
    
    def _detect_language(self, query: str) -> str:
        """Детекция языка по ключевым словам"""
        
        spanish_count = sum(1 for word in self.spanish_keywords if word in query)
        english_count = sum(1 for word in self.english_keywords if word in query)
        
        # Если есть явные испанские слова
        if spanish_count > english_count:
            return 'es'
        elif english_count > spanish_count:
            return 'en'
        else:
            # По умолчанию испанский (основной язык cannamente)
            return 'es'
    
    def _detect_query_type(self, query: str, session: ConversationSession) -> str:
        """Определение типа запроса по простым правилам"""
        
        # Reset patterns
        for pattern in self.reset_patterns:
            if pattern in query:
                return 'reset'
        
        # Follow-up indicators (только если есть предыдущие рекомендации)
        if session.has_strains():
            for pattern in self.follow_up_patterns:
                if pattern in query:
                    return 'follow_up'
        
        # Comparison indicators
        if any(word in query for word in ['comparar', 'compare', 'vs', 'versus']):
            return 'comparison'
        
        # По умолчанию новый поиск
        return 'new_search'
    
    def _extract_criteria(self, query: str) -> Dict[str, Any]:
        """Извлечение критериев поиска по ключевым словам"""
        
        criteria = {
            "effects": {"desired": [], "avoid": []},
            "medical_conditions": [],
            "potency": {},
            "flavors": {"preferred": [], "avoid": []},
            "conflicts_detected": []
        }
        
        # Поиск эффектов
        for effect_type, keywords in self.effect_keywords.items():
            if any(keyword in query for keyword in keywords):
                # Простое мапирование на стандартные эффекты
                effect_mapping = {
                    'sleep': 'Sleepy',
                    'energy': 'Energetic', 
                    'pain': 'Pain Relief',
                    'creativity': 'Creative',
                    'relaxation': 'Relaxed',
                    'focus': 'Focused'
                }
                
                if effect_type in effect_mapping:
                    criteria["effects"]["desired"].append(effect_mapping[effect_type])
        
        # Поиск потенциальности
        for potency_type, keywords in self.potency_keywords.items():
            if any(keyword in query for keyword in keywords):
                criteria["potency"]["thc"] = potency_type
                break
        
        # Медицинские состояния
        medical_conditions = []
        if any(word in query for word in ['dolor', 'pain', 'dolores', 'aches']):
            medical_conditions.append('Pain')
        if any(word in query for word in ['insomnio', 'insomnia', 'dormir', 'sleep']):
            medical_conditions.append('Insomnia')
        if any(word in query for word in ['ansiedad', 'anxiety', 'stress', 'estrés']):
            medical_conditions.append('Anxiety')
        
        criteria["medical_conditions"] = medical_conditions
        
        return criteria
    
    def _detect_topic_change(self, criteria: Dict[str, Any], session: ConversationSession) -> bool:
        """Простая детекция смены темы"""
        
        if not session.current_topic:
            return False
        
        # Если появились новые эффекты, отличающиеся от текущей темы
        desired_effects = criteria.get("effects", {}).get("desired", [])
        
        current_topic = session.current_topic.value
        
        # Простые правила смены темы
        opposite_pairs = [
            ('sleep', 'energy'),
            ('relaxation', 'focus'), 
            ('pain', 'recreation')
        ]
        
        for effect in desired_effects:
            effect_lower = effect.lower()
            for pair in opposite_pairs:
                if current_topic.lower() in pair[0] and effect_lower in pair[1]:
                    return True
                if current_topic.lower() in pair[1] and effect_lower in pair[0]:
                    return True
        
        return False
    
    def _determine_action(self, query_type: str, criteria: Dict[str, Any]) -> str:
        """Определение необходимого действия"""
        
        if query_type == 'reset':
            return 'reset'
        elif query_type == 'follow_up':
            return 'filter'  # Работать с существующими результатами
        elif query_type == 'comparison':
            return 'compare'
        elif criteria.get("effects") or criteria.get("medical_conditions"):
            return 'filter'  # Есть критерии для фильтрации
        else:
            return 'clarify'  # Нужны уточнения
    
    def _generate_response(self, query_type: str, language: str, criteria: Dict[str, Any]) -> str:
        """Генерация простого ответа"""
        
        responses = {
            'es': {
                'new_search': 'Te ayudo a encontrar variedades que se ajusten a tus necesidades.',
                'follow_up': 'Trabajemos con las variedades que te recomendé anteriormente.',
                'comparison': 'Puedo ayudarte a comparar las opciones disponibles.',
                'reset': 'Perfecto, empecemos de nuevo. ¿Qué efectos buscas?',
                'clarification': '¿Podrías ser más específico sobre qué efectos buscas?'
            },
            'en': {
                'new_search': 'I can help you find strains that match your needs.',
                'follow_up': 'Let me work with the strains I previously recommended.',
                'comparison': 'I can help you compare the available options.',
                'reset': 'Perfect, let\'s start fresh. What effects are you looking for?',
                'clarification': 'Could you be more specific about what effects you\'re looking for?'
            }
        }
        
        lang_responses = responses.get(language, responses['es'])
        return lang_responses.get(query_type, lang_responses['clarification'])
    
    def _generate_quick_actions(self, query_type: str, language: str, session: ConversationSession) -> List[str]:
        """Генерация простых quick actions"""
        
        actions = []
        
        if query_type == 'follow_up' and session.has_strains():
            if language == 'es':
                actions.extend(['Ver más fuerte', 'Ver más suave', 'Comparar opciones'])
            else:
                actions.extend(['Show strongest', 'Show mildest', 'Compare options'])
        
        elif query_type == 'new_search':
            if language == 'es':
                actions.extend(['Para dormir', 'Para energía', 'Para dolor', 'Para creatividad'])
            else:
                actions.extend(['For sleep', 'For energy', 'For pain', 'For creativity'])
        
        # Всегда добавляем reset опцию если есть история
        if session.conversation_history or session.has_strains():
            reset_action = 'Nueva búsqueda' if language == 'es' else 'New search'
            actions.append(reset_action)
        
        return actions[:4]  # Максимум 4 действия