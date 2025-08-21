from typing import List, Dict, Any, Optional
from app.models.session import ConversationSession
from app.models.schemas import Strain
from app.db.repository import StrainRepository
import logging

logger = logging.getLogger(__name__)


class ContextProvider:
    """
    Context Provider для Smart Query Analyzer v3.0
    Отвечает за подготовку полного контекста для AI анализа
    """
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
    
    def get_session_strains(self, session: ConversationSession) -> List[Strain]:
        """Получение сортов из контекста сессии с полными данными"""
        
        if not session.has_strains():
            logger.info("No strains in session context")
            return []
        
        # Получаем ID последних рекомендованных сортов
        strain_ids = session.get_last_strains()
        logger.info(f"Getting {len(strain_ids)} strains from session: {strain_ids}")
        
        # Загружаем полные данные сортов с связанными объектами
        strains = []
        for strain_id in strain_ids:
            strain = self.repository.get_strain_with_relations(strain_id)
            if strain:
                strains.append(strain)
            else:
                logger.warning(f"Strain {strain_id} not found in database")
        
        logger.info(f"Loaded {len(strains)} strains with full data")
        return strains
    
    def build_strain_context(self, strains: List[Strain]) -> List[Dict[str, Any]]:
        """Построение детального контекста сортов для AI"""
        
        strains_context = []
        for i, strain in enumerate(strains):
            # Очистка названия от лишних символов
            clean_name = strain.name.split(' | ')[0] if strain.name else strain.name
            
            strain_context = {
                "index": i,  # Индекс для ссылок пользователя
                "id": strain.id,
                "name": clean_name,
                "category": strain.category,
                "cannabinoids": {
                    "thc": self._clean_cannabinoid_value(strain.thc),
                    "cbd": self._clean_cannabinoid_value(strain.cbd),
                    "cbg": self._clean_cannabinoid_value(strain.cbg)
                },
                "effects": {
                    "feelings": [f.name for f in strain.feelings] if strain.feelings else [],
                    "helps_with": [h.name for h in strain.helps_with] if strain.helps_with else [],
                    "negatives": [n.name for n in strain.negatives] if strain.negatives else []
                },
                "flavors": [fl.name for fl in strain.flavors] if strain.flavors else [],
                "data_quality": self._assess_strain_data_quality(strain)
            }
            strains_context.append(strain_context)
        
        return strains_context
    
    def build_conversation_context(self, session: ConversationSession, max_entries: int = 3) -> str:
        """Построение контекста разговора для AI"""
        
        if not session.conversation_history:
            return "No previous conversation"
        
        # Берем последние записи разговора
        recent_entries = session.conversation_history[-max_entries:]
        
        context_parts = []
        for entry in recent_entries:
            user_msg = entry.get('query', '')
            ai_response = entry.get('response', '')
            
            # Сокращаем длинные сообщения
            user_short = user_msg[:80] + "..." if len(user_msg) > 80 else user_msg
            ai_short = ai_response[:80] + "..." if len(ai_response) > 80 else ai_response
            
            context_parts.append(f"User: {user_short} | AI: {ai_short}")
        
        return " || ".join(context_parts)
    
    def build_user_preferences_context(self, session: ConversationSession) -> Dict[str, Any]:
        """Построение контекста пользовательских предпочтений"""
        
        preferences = {}
        for key, values in session.user_preferences.items():
            if isinstance(values, set):
                preferences[key] = list(values)
            else:
                preferences[key] = values
        
        return preferences
    
    def build_session_metadata(self, session: ConversationSession) -> Dict[str, Any]:
        """Метаданные сессии для контекста"""
        
        return {
            "session_id": session.session_id,
            "detected_language": session.detected_language,
            "current_topic": session.current_topic.value if session.current_topic else None,
            "is_restored": session.is_restored,
            "conversation_length": len(session.conversation_history),
            "recommendations_count": len(session.recommended_strains_history),
            "has_active_context": session.has_strains()
        }
    
    def get_full_context(
        self,
        user_query: str,
        session: ConversationSession
    ) -> Dict[str, Any]:
        """Получение полного контекста для AI анализа"""
        
        # Получаем сорта из сессии
        session_strains = self.get_session_strains(session)
        
        # Строим полный контекст
        full_context = {
            "user_query": user_query,
            "session_strains": self.build_strain_context(session_strains),
            "conversation_context": self.build_conversation_context(session),
            "user_preferences": self.build_user_preferences_context(session),
            "session_metadata": self.build_session_metadata(session),
            "context_summary": {
                "has_strains": len(session_strains) > 0,
                "strain_count": len(session_strains),
                "primary_language": session.detected_language or "es",
                "conversation_turns": len(session.conversation_history)
            }
        }
        
        logger.info(f"Built full context: {len(session_strains)} strains, {len(session.conversation_history)} turns")
        return full_context
    
    def _clean_cannabinoid_value(self, value: Optional[str]) -> Optional[str]:
        """Очистка значений каннабиноидов"""
        
        if not value:
            return None
        
        # Приведение к строке и очистка
        str_value = str(value).strip()
        
        # Проверка на невалидные значения
        invalid_values = ['n/a', 'none', 'null', 'unknown', '', '0', '0.0', '0.00']
        if str_value.lower() in invalid_values:
            return None
        
        try:
            # Проверка что это число
            float(str_value)
            return str_value
        except ValueError:
            return None
    
    def _assess_strain_data_quality(self, strain: Strain) -> Dict[str, Any]:
        """Оценка качества данных сорта"""
        
        quality = {
            "has_valid_thc": self._clean_cannabinoid_value(strain.thc) is not None,
            "has_valid_cbd": self._clean_cannabinoid_value(strain.cbd) is not None,
            "has_effects": bool(strain.feelings),
            "has_medical_uses": bool(strain.helps_with),
            "has_flavors": bool(strain.flavors),
            "completeness_score": 0.0
        }
        
        # Расчет полноты данных
        total_fields = 5
        filled_fields = sum([
            quality["has_valid_thc"],
            quality["has_valid_cbd"], 
            quality["has_effects"],
            quality["has_medical_uses"],
            quality["has_flavors"]
        ])
        
        quality["completeness_score"] = filled_fields / total_fields
        quality["is_complete"] = quality["completeness_score"] >= 0.6
        quality["missing_critical"] = not quality["has_valid_thc"] and not quality["has_effects"]
        
        return quality
    
    def get_available_actions(self) -> List[str]:
        """Получение доступных системных действий"""
        
        return [
            "sort_strains",      # Сортировка сортов по критериям
            "filter_strains",    # Фильтрация сортов по условиям
            "select_strains",    # Выбор конкретных сортов
            "explain_strains",   # Объяснение характеристик
            "expand_search"      # Поиск новых сортов
        ]
    
    def validate_context_completeness(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация полноты контекста"""
        
        validation = {
            "is_complete": True,
            "missing_fields": [],
            "warnings": []
        }
        
        # Проверка обязательных полей
        required_fields = ["user_query", "session_strains", "session_metadata"]
        for field in required_fields:
            if field not in context:
                validation["missing_fields"].append(field)
                validation["is_complete"] = False
        
        # Предупреждения
        if not context.get("session_strains"):
            validation["warnings"].append("No strains in session context")
        
        if not context.get("conversation_context"):
            validation["warnings"].append("No conversation history")
        
        return validation