import logging
from typing import List, Optional, Dict, Any
from app.models.session import ConversationSession
from app.models.schemas import ChatResponse, CompactStrain, CompactFeeling, CompactHelpsWith, CompactNegative, CompactFlavor, Strain
from app.core.smart_query_analyzer import SmartQueryAnalyzer, SmartAnalysis
from app.core.context_provider import ContextProvider
from app.core.universal_action_executor import UniversalActionExecutor
from app.core.session_manager import get_session_manager
from app.db.repository import StrainRepository
from app.core.llm_interface import get_llm
from app.core.intent_detection import IntentType
from app.core.dialog_policy import extract_request_signals, decide_action_hint, detect_language
import os

logger = logging.getLogger(__name__)


class SmartRAGService:
    """
    Smart RAG Service v3.0 - Интеллектуальный сервис с AI-driven обработкой запросов
    
    Основные принципы:
    - AI определяет план действий для каждого запроса
    - Минимум хардкода, максимум AI рассуждений
    - Автоматическое исключение invalid данных
    - Полный контекст для принятия решений
    """
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
        self.session_manager = get_session_manager()
        
        # Инициализация компонентов v3.0
        self.llm_interface = get_llm()
        self.smart_analyzer = SmartQueryAnalyzer(self.llm_interface)
        self.context_provider = ContextProvider(repository)
        self.action_executor = UniversalActionExecutor(repository)
        
        # Проверка включения Smart Query Executor
        self.use_smart_executor = os.getenv('USE_SMART_EXECUTOR', 'true').lower() == 'true'
        
        if not self.use_smart_executor:
            logger.warning("Smart Query Executor disabled, falling back to legacy mode")
    
    def process_contextual_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        history: Optional[List[str]] = None,
        source_platform: Optional[str] = None
    ) -> ChatResponse:
        """
        Главный метод обработки запросов с Smart Query Executor v3.0
        """
        
        logger.info(f"Processing query with Smart RAG v3.0: {query[:50]}...")
        
        # 1. Управление сессией
        session = self.session_manager.get_or_restore_session(session_id)
        
        # 2. Проверка использования Smart Executor
        if not self.use_smart_executor:
            # Fallback к legacy обработке
            return self._legacy_process_query(query, session)
        
        # 3. Получение полного контекста
        full_context = self.context_provider.get_full_context(query, session)
        session_strains = self.context_provider.get_session_strains(session)
        
        # 4. Обработка специальных команд (reset)
        if self._is_reset_command(query):
            return self._handle_reset(session, query)
        
        # 5. Подсказки политики диалога (категория/эффекты/вкусы/сортировка)
        policy_signals = extract_request_signals(query)
        policy_hint = decide_action_hint(session, session_strains, policy_signals)

        # 6. Smart анализ запроса с полным контекстом + policy
        try:
            smart_analysis = self.smart_analyzer.analyze_query(
                query, session, session_strains, full_context, policy_hint
            )
            logger.info(f"Smart analysis: {smart_analysis.action_plan.primary_action}, confidence: {smart_analysis.confidence}")
        except Exception as e:
            logger.error(f"Smart analysis failed: {e}")
            # Fallback к legacy обработке
            return self._legacy_process_query(query, session)
        
        # 7. Если политика требует расширить поиск (новая категория/эффекты, контекст плохо совпадает)
        if policy_hint.get("force_expand_search") and smart_analysis.action_plan.primary_action not in ["search_strains", "expand_search"]:
            logger.info("Dialog policy forces expand_search due to mismatch with session context")
            smart_analysis.action_plan.primary_action = "expand_search"

        # Вливаем предложенные фильтры/сортировку в параметры (без перезаписи уже заданных AI)
        if policy_hint.get("suggested_filters"):
            params_filters = smart_analysis.action_plan.parameters.setdefault("filters", {})
            for k, v in policy_hint["suggested_filters"].items():
                params_filters.setdefault(k, v)
        if policy_hint.get("suggested_sort") and "sort" not in smart_analysis.action_plan.parameters:
            smart_analysis.action_plan.parameters["sort"] = policy_hint["suggested_sort"]

        # Язык: если AI не указал, используем детекцию политики
        if not smart_analysis.detected_language:
            smart_analysis.detected_language = policy_hint.get("language") or 'en'

        # 8. Обработка случаев недостаточного контекста
        if smart_analysis.action_plan.primary_action in ['sort_strains', 'filter_strains', 'select_strains'] and not session_strains:
            # Если пытаемся сортировать/фильтровать/выбирать, но нет сортов в сессии - делаем поиск
            logger.info(f"Converting {smart_analysis.action_plan.primary_action} to search_strains due to empty session")
            smart_analysis.action_plan.primary_action = 'search_strains'
        elif smart_analysis.action_plan.primary_action in ['expand_search'] and not session_strains:
            # Для expand_search без контекста - просто выполняем поиск
            pass
        
        # 9. Выполнение действия по AI плану
        result_strains = self.action_executor.execute_action(
            smart_analysis.action_plan,
            session_strains
        )
        
        # 10. Обновление сессии
        self._update_session(session, query, smart_analysis, result_strains)
        
        # 11. Сохранение сессии
        self.session_manager.save_session_with_backup(session)
        
        # 12. Построение ответа
        return self._build_smart_response(smart_analysis, result_strains, session)
    
    def _handle_reset(self, session: ConversationSession, query: str) -> ChatResponse:
        """Обработка команды сброса"""
        
        logger.info("Handling reset command")
        
        # Очистка контекста сессии
        session.recommended_strains_history = []
        session.conversation_history = []
        session.current_topic = None
        session.previous_topics = []
        
        # Определение языка для ответа
        language = detect_language(query)
        
        responses = {
            'es': "Perfecto, empecemos de nuevo. ¿Qué tipo de efectos buscas?",
            'en': "Perfect, let's start fresh. What kind of effects are you looking for?"
        }
        
        quick_actions = self._get_new_search_suggestions(language)
        
        return ChatResponse(
            response=responses.get(language, responses['es']),
            recommended_strains=[],
            detected_intent='reset',
            filters_applied={},
            session_id=session.session_id,
            query_type='reset',
            language=language,
            confidence=1.0,
            quick_actions=quick_actions,
            is_restored=session.is_restored,
            is_fallback=False
        )
    
    def _handle_no_context(self, analysis: SmartAnalysis, session: ConversationSession) -> ChatResponse:
        """Обработка запросов без контекста"""
        
        logger.info("Handling no context situation")
        
        responses = {
            'es': "No tengo variedades anteriores para comparar. ¿Qué efectos buscas?",
            'en': "I don't have previous strains to compare. What effects are you looking for?"
        }
        
        quick_actions = self._get_new_search_suggestions(analysis.detected_language)
        
        return ChatResponse(
            response=responses.get(analysis.detected_language, responses['es']),
            recommended_strains=[],
            detected_intent='no_context',
            filters_applied={},
            session_id=session.session_id,
            query_type='clarification',
            language=analysis.detected_language,
            confidence=1.0,
            quick_actions=quick_actions,
            is_restored=session.is_restored,
            is_fallback=analysis.is_fallback
        )
    
    def _build_smart_response(
        self,
        analysis: SmartAnalysis,
        strains: List[Strain],
        session: ConversationSession
    ) -> ChatResponse:
        """Построение ответа на основе Smart анализа"""
        
        # Используем готовый natural response от AI с подстановкой реальных названий
        response_text = self._substitute_strain_placeholders(analysis.natural_response, strains)
        
        # Компактные сорта для UI
        compact_strains = self._build_compact_strains(strains)
        
        # Динамические quick actions (либо от AI, либо сгенерированные)
        quick_actions = analysis.suggested_follow_ups or self._generate_contextual_actions(
            strains, analysis.detected_language, session
        )
        
        # Добавление индикаторов AI reasoning (опционально для отладки)
        if os.getenv('ENABLE_AI_REASONING_DEBUG', 'false').lower() == 'true':
            response_text += f"\n\n🤖 Reasoning: {analysis.action_plan.reasoning}"
        
        return ChatResponse(
            response=response_text,
            recommended_strains=compact_strains,
            detected_intent=analysis.action_plan.primary_action,
            filters_applied=analysis.action_plan.parameters,
            session_id=session.session_id,
            query_type=analysis.action_plan.primary_action,
            language=analysis.detected_language,
            confidence=analysis.confidence,
            quick_actions=quick_actions,
            is_restored=session.is_restored,
            is_fallback=analysis.is_fallback,
            warnings=[] if analysis.confidence > 0.7 else ["Low confidence analysis"]
        )
    
    def _update_session(
        self,
        session: ConversationSession,
        query: str,
        analysis: SmartAnalysis,
        strains: List[Strain]
    ):
        """Обновление сессии после smart обработки"""
        
        # Обновление языка
        if analysis.detected_language:
            session.detected_language = analysis.detected_language
        
        # Добавление сортов в историю
        if strains:
            strain_ids = [s.id for s in strains]
            session.add_strain_recommendation(strain_ids)
            logger.info(f"Added {len(strain_ids)} strains to session history")
        
        # Обновление темы разговора (попытка определить по действию)
        if analysis.action_plan.primary_action == 'expand_search':
            # Новый поиск - возможно смена темы
            if 'sleep' in query.lower() or 'dormir' in query.lower():
                session.update_topic(IntentType.SLEEP)
            elif 'energy' in query.lower() or 'energía' in query.lower():
                session.update_topic(IntentType.ENERGY)
        
        # Обновление предпочтений (если есть в параметрах действия)
        if 'criteria' in analysis.action_plan.parameters:
            criteria = analysis.action_plan.parameters['criteria']
            if isinstance(criteria, dict) and 'effects' in criteria:
                if 'desired' in criteria['effects']:
                    session.update_preferences('preferred_effects', criteria['effects']['desired'])
        
        # Добавление записи в историю разговора
        session.add_conversation_entry(
            query=query,
            response=analysis.natural_response,
            intent=session.current_topic
        )
        
        # Обновление времени активности
        session.update_activity()
    
    def _build_compact_strains(self, strains: List[Strain]) -> List[CompactStrain]:
        """Создание компактных объектов сортов для UI"""
        
        compact_strains = []
        for strain in strains:
            # Очистка имени
            clean_name = strain.name.split(' | ')[0] if strain.name else strain.name
            
            compact_strain = CompactStrain(
                id=strain.id,
                name=clean_name,
                cbd=strain.cbd,
                thc=strain.thc,
                cbg=strain.cbg,
                category=strain.category,
                slug=strain.slug,
                url=self._build_strain_url(strain.slug),
                feelings=[CompactFeeling(name=f.name) for f in strain.feelings] if strain.feelings else [],
                helps_with=[CompactHelpsWith(name=h.name) for h in strain.helps_with] if strain.helps_with else [],
                negatives=[CompactNegative(name=n.name) for n in strain.negatives] if strain.negatives else [],
                flavors=[CompactFlavor(name=fl.name) for fl in strain.flavors] if strain.flavors else []
            )
            compact_strains.append(compact_strain)
        
        return compact_strains
    
    def _substitute_strain_placeholders(self, response_text: str, strains: List[Strain]) -> str:
        """Заменяет плейсхолдеры [strain_name], [Strain Name] на реальные названия сортов"""
        
        if not strains or not response_text:
            return response_text
        
        # Получаем первый сорт как основной для замены
        primary_strain = strains[0]
        primary_name = primary_strain.name.split(' | ')[0] if primary_strain.name else "Unknown"
        
        # Паттерны плейсхолдеров для замены
        placeholders = [
            "[strain_name]", "[Strain Name]", "[strain name]", "[STRAIN_NAME]",
            "[nombre de la cepa]", "[Nombre de la Cepa]", "[NOMBRE DE LA CEPA]",
            "[cepa]", "[Cepa]", "[CEPA]", "[variety]", "[Variety]", "[VARIETY]",
            "Nombre de la variedad", "'Nombre de la variedad'", "[Nombre de la variedad]",
            "nombre de la variedad", "'nombre de la variedad'", "[nombre de la variedad]",
            "Strain Name", "'Strain Name'", "strain name", "'strain name'"
        ]
        
        result_text = response_text
        
        # Заменяем все плейсхолдеры на название первого сорта
        for placeholder in placeholders:
            result_text = result_text.replace(placeholder, primary_name)
        
        # Если есть несколько сортов, добавляем их через запятую для некоторых случаев
        if len(strains) > 1:
            # Ищем конструкции типа "cepas como [strain_name]" и заменяем на список
            strain_names = [s.name.split(' | ')[0] for s in strains[:3]]  # Первые 3 сорта
            strain_list = ", ".join(strain_names)
            
            # Паттерны для множественного числа
            multiple_patterns = [
                f"cepas como {primary_name}",
                f"strains like {primary_name}", 
                f"variedades como {primary_name}",
                f"varieties like {primary_name}"
            ]
            
            for pattern in multiple_patterns:
                if pattern in result_text:
                    replacement = pattern.replace(primary_name, strain_list)
                    result_text = result_text.replace(pattern, replacement)
        
        return result_text
    
    def _build_strain_url(self, strain_slug: str) -> Optional[str]:
        """Построение URL для сорта"""
        if not strain_slug:
            return None
        base_url = os.getenv('CANNAMENTE_BASE_URL')
        url_pattern = os.getenv('STRAIN_URL_PATTERN', '/strain/{slug}/')
        return f"{base_url}{url_pattern.format(slug=strain_slug)}"
    
    def _generate_contextual_actions(
        self,
        strains: List[Strain],
        language: str,
        session: ConversationSession
    ) -> List[str]:
        """Генерация контекстных quick actions"""
        
        actions = []
        
        if len(strains) > 1:
            # Действия для множественного выбора
            if language == 'es':
                actions.append("Ver el más potente")
                actions.append("Ver el más suave") 
                actions.append("Comparar efectos")
            else:
                actions.append("Show strongest")
                actions.append("Show mildest")
                actions.append("Compare effects")
        
        # Добавляем опцию поиска новых сортов
        search_action = "Buscar más opciones" if language == 'es' else "Find more options"
        actions.append(search_action)
        
        # Добавляем reset если есть история
        if session.conversation_history:
            reset_action = "Empezar nueva búsqueda" if language == 'es' else "Start new search"
            actions.append(reset_action)
        
        return actions[:4]  # Максимум 4 действия
    
    def _get_new_search_suggestions(self, language: str) -> List[str]:
        """Получить предложения для нового поиска"""
        
        if language == 'es':
            return ['Para dormir', 'Para energía', 'Para dolor', 'Para creatividad']
        else:
            return ['For sleep', 'For energy', 'For pain', 'For creativity']
    
    def _is_reset_command(self, query: str) -> bool:
        """Проверка команды сброса"""
        
        query_lower = query.lower()
        reset_indicators = [
            'empezar de nuevo', 'start over', 'nueva consulta', 'new search',
            'reset', 'reiniciar', 'comenzar otra vez'
        ]
        
        return any(indicator in query_lower for indicator in reset_indicators)
    
    def _detect_language(self, text: str) -> str:
        """Простая детекция языка"""
        
        spanish_indicators = ['para', 'necesito', 'quiero', 'cuál', 'qué', 'más', 'mejor']
        text_lower = text.lower()
        
        spanish_count = sum(1 for word in spanish_indicators if word in text_lower)
        return 'es' if spanish_count > 0 else 'en'
    
    def _legacy_process_query(
        self,
        query: str,
        session: ConversationSession
    ) -> ChatResponse:
        """Fallback к legacy обработке (оптимизированный RAG v2.0)"""
        
        logger.info("Using legacy processing mode")
        
        # Импорт legacy сервиса
        from app.core.optimized_rag_service import OptimizedContextualRAGService
        
        # Создание legacy сервиса и обработка
        legacy_service = OptimizedContextualRAGService(self.repository)
        return legacy_service.process_contextual_query(query, session.session_id)
    
    def get_service_info(self) -> Dict[str, Any]:
        """Информация о сервисе для мониторинга"""
        
        return {
            "service_name": "SmartRAGService",
            "version": "3.0",
            "smart_executor_enabled": self.use_smart_executor,
            "components": [
                "SmartQueryAnalyzer",
                "ContextProvider", 
                "ActionExecutor",
                "SessionManager"
            ],
            "fallback_available": True
        }