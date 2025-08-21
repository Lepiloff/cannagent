import logging
from typing import List, Optional, Dict, Any
from app.models.session import ConversationSession, UnifiedAnalysis
from app.models.schemas import ChatResponse, CompactStrain, CompactFeeling, CompactHelpsWith, CompactNegative, CompactFlavor, Strain
from app.core.unified_processor import UnifiedLLMProcessor
from app.core.fallback_analyzer import RuleBasedFallbackAnalyzer
from app.core.conflict_resolver import CriteriaConflictResolver
from app.core.session_manager import get_session_manager
from app.core.adaptive_search import AdaptiveStrainSearch
from app.db.repository import StrainRepository
from app.core.intent_detection import IntentType
import os

logger = logging.getLogger(__name__)


class OptimizedContextualRAGService:
    """Оптимизированный RAG с единым LLM вызовом и контекстом"""
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
        self.session_manager = get_session_manager()
        self.unified_processor = UnifiedLLMProcessor()
        self.fallback_analyzer = RuleBasedFallbackAnalyzer()
        self.conflict_resolver = CriteriaConflictResolver()
        self.adaptive_search = AdaptiveStrainSearch(repository)
        
    def process_contextual_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        history: Optional[List[str]] = None,
        source_platform: Optional[str] = None
    ) -> ChatResponse:
        """Главный метод с оптимизацией и fallbacks"""
        
        # 1. Управление сессией с восстановлением
        session = self.session_manager.get_or_restore_session(session_id)
        
        # 2. ЕДИНЫЙ анализ через LLM или fallback
        try:
            analysis = self.unified_processor.analyze_complete(query, session)
            logger.info(f"LLM analysis successful: {analysis.query_type}")
        except Exception as e:
            logger.warning(f"LLM failed, using fallback: {e}")
            analysis = self.fallback_analyzer.analyze(query, session)
        
        # 3. Обработка команды сброса
        if analysis.query_type == 'reset':
            return self._handle_reset(session, analysis)
        
        # 4. Обработка edge cases
        if analysis.query_type == 'follow_up' and not session.has_strains():
            return self._handle_no_context(analysis.detected_language, session.session_id)
        
        # 5. Разрешение конфликтов в критериях
        if analysis.criteria:
            resolved_criteria, conflicts = self.conflict_resolver.resolve_conflicts(
                analysis.criteria, query
            )
            analysis.criteria = resolved_criteria
            if conflicts:
                analysis.warnings = (analysis.warnings or []) + conflicts
        
        # 6. Обработка по типу запроса
        strains = self._process_by_type(analysis, session)
        
        # 7. Обновление сессии
        self._update_session(session, query, analysis, strains)
        
        # 8. Сохранение с backup
        self.session_manager.save_session_with_backup(session)
        
        # 9. Построение ответа
        return self._build_optimized_response(analysis, strains, session)
    
    def _handle_reset(self, session: ConversationSession, analysis: UnifiedAnalysis) -> ChatResponse:
        """Обработка сброса контекста"""
        
        # Сохраняем только базовые предпочтения
        preserved_preferences = session.user_preferences.copy()
        
        # Очищаем историю
        session.recommended_strains_history = []
        session.conversation_history = []
        session.current_topic = None
        session.previous_topics = []
        
        # Сохраняем некоторые глобальные предпочтения если есть
        if preserved_preferences:
            # Оставляем только основные предпочтения, убираем специфичные
            global_prefs = {}
            for key, values in preserved_preferences.items():
                if key in ['preferred_potency', 'medical_conditions']:
                    global_prefs[key] = values
            session.user_preferences = global_prefs
        
        responses = {
            'es': "Perfecto, empecemos de nuevo. ¿Qué tipo de efectos buscas?",
            'en': "Perfect, let's start fresh. What kind of effects are you looking for?"
        }
        
        return ChatResponse(
            response=responses.get(analysis.detected_language, responses['es']),
            recommended_strains=[],
            detected_intent='reset',
            filters_applied={},
            session_id=session.session_id,
            query_type='reset',
            language=analysis.detected_language,
            confidence=1.0,
            quick_actions=self._get_new_search_suggestions(analysis.detected_language),
            is_restored=session.is_restored,
            is_fallback=analysis.is_fallback
        )
    
    def _handle_no_context(self, language: str, session_id: str) -> ChatResponse:
        """Обработка follow-up без контекста"""
        
        responses = {
            'es': "No tengo variedades anteriores para comparar. ¿Qué efectos buscas?",
            'en': "I don't have previous strains to compare. What effects are you looking for?"
        }
        
        return ChatResponse(
            response=responses.get(language, responses['es']),
            recommended_strains=[],
            detected_intent='no_context',
            filters_applied={},
            session_id=session_id,
            query_type='clarification',
            language=language,
            confidence=1.0,
            quick_actions=self._get_new_search_suggestions(language),
            is_restored=False,
            is_fallback=False
        )
    
    def _process_by_type(
        self,
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[Strain]:
        """Обработка в зависимости от типа с оптимизацией"""
        
        if analysis.query_type == 'follow_up':
            # Работаем с существующими сортами
            strain_ids = session.get_last_strains()
            logger.info(f"Follow-up: session has {len(session.recommended_strains_history)} strain groups")
            logger.info(f"Follow-up: last strain IDs: {strain_ids}")
            if not strain_ids:
                logger.warning("Follow-up: No strains in session context!")
                return []
            
            strains = []
            for strain_id in strain_ids:
                strain = self.repository.get_strain_with_relations(strain_id)
                if strain:
                    strains.append(strain)
            
            # Для follow-up запросов НЕ применяем фильтрацию - пользователь работает с уже найденными сортами
            # Применяем только сортировку если нужно, но не исключаем сорта из контекста
            if analysis.criteria and analysis.criteria.get('potency'):
                potency_pref = analysis.criteria['potency'].get('thc')
                if potency_pref == 'higher':
                    strains.sort(key=lambda s: float(s.thc) if s.thc else 0, reverse=True)
                elif potency_pref == 'lower':
                    strains.sort(key=lambda s: float(s.thc) if s.thc else 0)
            
            # НЕ применяем _apply_criteria_filters для follow-up запросов
            
            logger.info(f"Follow-up processing: {len(strains)} strains from context")
            return strains
        
        elif analysis.query_type == 'new_search':
            # Новый поиск с учетом предпочтений
            return self._optimized_search(analysis, session)
        
        elif analysis.query_type == 'comparison':
            # Сравнение из контекста
            return self._handle_comparison(analysis, session)
        
        elif analysis.query_type == 'detail_request':
            # Детали конкретного сорта
            return self._handle_detail_request(analysis, session)
        
        else:
            # Default - показываем последние если есть, иначе общий поиск
            if session.has_strains():
                strain_ids = session.get_last_strains()
                strains = []
                for strain_id in strain_ids[:3]:  # Максимум 3
                    strain = self.repository.get_strain_with_relations(strain_id)
                    if strain:
                        strains.append(strain)
                return strains
            else:
                # Общий поиск если нет контекста
                return self._optimized_search(analysis, session)
    
    def _optimized_search(
        self,
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[Strain]:
        """Оптимизированный поиск с адаптивными фильтрами"""
        
        # Подготовка критериев из анализа и сессии
        merged_criteria = self._merge_filters(analysis.criteria, session.user_preferences)
        
        # Используем адаптивный поиск
        strains = self.adaptive_search.search_with_adaptive_filters(
            query=analysis.original_query,
            criteria=merged_criteria,
            limit=5
        )
        
        logger.info(f"Adaptive search: found {len(strains)} strains")
        
        # Дополнительная диагностика если нужно
        if logger.isEnabledFor(logging.DEBUG):
            explanation = self.adaptive_search.explain_search_strategy(
                analysis.original_query,
                merged_criteria,
                strains
            )
            logger.debug(f"Search explanation: {explanation}")
        
        return strains
    
    def _handle_comparison(
        self,
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[Strain]:
        """Обработка сравнения сортов"""
        
        if not session.has_strains():
            return []
        
        # Получаем последние рекомендованные сорта
        strain_ids = session.get_last_strains()
        strains = []
        for strain_id in strain_ids:
            strain = self.repository.get_strain_with_relations(strain_id)
            if strain:
                strains.append(strain)
        
        # Для сравнения можем отсортировать по релевантным критериям
        if analysis.criteria and analysis.criteria.get('potency'):
            potency_pref = analysis.criteria['potency'].get('thc')
            if potency_pref == 'higher':
                strains.sort(key=lambda s: float(s.thc) if s.thc else 0, reverse=True)
            elif potency_pref == 'lower':
                strains.sort(key=lambda s: float(s.thc) if s.thc else 0)
        
        logger.info(f"Comparison: {len(strains)} strains from context")
        return strains[:3]  # Максимум 3 для сравнения
    
    def _handle_detail_request(
        self,
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[Strain]:
        """Обработка запроса деталей конкретного сорта"""
        
        # Попытка найти упомянутый сорт
        if analysis.criteria and analysis.criteria.get('strain_reference'):
            strain_ref = analysis.criteria['strain_reference']
            
            if strain_ref.get('type') == 'name':
                # Поиск по имени
                strain_name = strain_ref.get('value', '')
                strains = self.repository.search_strains_by_name(strain_name)
                if strains:
                    return strains[:1]
            
            elif strain_ref.get('type') == 'index' and session.has_strains():
                # Поиск по индексу в последних рекомендациях
                try:
                    index = int(strain_ref.get('value', '0'))
                    strain_ids = session.get_last_strains()
                    if 0 <= index < len(strain_ids):
                        strain = self.repository.get_strain_with_relations(strain_ids[index])
                        return [strain] if strain else []
                except (ValueError, IndexError):
                    pass
        
        # Если не нашли специфичный сорт, возвращаем последние рекомендации
        if session.has_strains():
            strain_ids = session.get_last_strains()
            strains = []
            for strain_id in strain_ids[:1]:  # Только первый
                strain = self.repository.get_strain_with_relations(strain_id)
                if strain:
                    strains.append(strain)
            return strains
        
        return []
    
    def _apply_criteria_filters(self, strains: List[Strain], criteria: Dict[str, Any]) -> List[Strain]:
        """Применение критериев фильтрации к существующим сортам"""
        
        if not criteria or not strains:
            return strains
        
        filtered_strains = []
        
        for strain in strains:
            # Проверка эффектов
            if 'effects' in criteria:
                effects = criteria['effects']
                
                # Нужные эффекты
                if effects.get('desired'):
                    strain_effects = {f.name for f in strain.feelings} if strain.feelings else set()
                    required_effects = set(effects['desired'])
                    if not (required_effects & strain_effects):  # Нет пересечения
                        continue
                
                # Избегаемые эффекты
                if effects.get('avoid'):
                    strain_effects = {f.name for f in strain.feelings} if strain.feelings else set()
                    avoid_effects = set(effects['avoid'])
                    if strain_effects & avoid_effects:  # Есть пересечение с избегаемыми
                        continue
            
            # Проверка потенциальности
            if 'potency' in criteria and strain.thc:
                potency = criteria['potency']
                if potency.get('thc') == 'higher' and float(strain.thc) < 15.0:
                    continue
                elif potency.get('thc') == 'lower' and float(strain.thc) > 15.0:
                    continue
            
            filtered_strains.append(strain)
        
        logger.info(f"Filtered {len(strains)} -> {len(filtered_strains)} strains")
        return filtered_strains
    
    def _merge_filters(
        self, 
        criteria: Optional[Dict[str, Any]], 
        user_preferences: Dict[str, set]
    ) -> Dict[str, Any]:
        """Объединение критериев анализа с предпочтениями пользователя"""
        
        merged = {}
        
        # Начинаем с критериев анализа
        if criteria:
            merged.update(criteria)
        
        # Добавляем предпочтения пользователя
        if user_preferences:
            # Эффекты
            if 'preferred_effects' in user_preferences:
                if 'effects' not in merged:
                    merged['effects'] = {}
                if 'desired' not in merged['effects']:
                    merged['effects']['desired'] = []
                merged['effects']['desired'].extend(list(user_preferences['preferred_effects']))
            
            if 'avoid_effects' in user_preferences:
                if 'effects' not in merged:
                    merged['effects'] = {}
                if 'avoid' not in merged['effects']:
                    merged['effects']['avoid'] = []
                merged['effects']['avoid'].extend(list(user_preferences['avoid_effects']))
        
        return merged
    
    def _update_session(
        self,
        session: ConversationSession,
        query: str,
        analysis: UnifiedAnalysis,
        strains: List[Strain]
    ):
        """Обновление сессии после обработки"""
        
        # Обновляем язык если детектирован
        if analysis.detected_language:
            session.detected_language = analysis.detected_language
        
        # Добавляем рекомендации в историю
        if strains:
            strain_ids = [s.id for s in strains]
            logger.info(f"Saving {len(strain_ids)} strains to session: {strain_ids}")
            session.add_strain_recommendation(strain_ids)
            logger.info(f"Session now has {len(session.recommended_strains_history)} strain groups")
        
        # Обновляем тему разговора
        if analysis.query_type == 'new_search' and analysis.criteria:
            # Попытка определить intent из критериев
            effects = analysis.criteria.get('effects', {}).get('desired', [])
            if 'Sleepy' in effects or 'Relaxed' in effects:
                session.update_topic(IntentType.SLEEP)
            elif 'Energetic' in effects or 'Uplifted' in effects:
                session.update_topic(IntentType.ENERGY)
            elif 'Creative' in effects or 'Euphoric' in effects:
                session.update_topic(IntentType.CREATIVITY)
            elif 'Focused' in effects:
                session.update_topic(IntentType.FOCUS)
        
        # Обновляем предпочтения
        if analysis.criteria:
            effects = analysis.criteria.get('effects', {})
            if effects.get('desired'):
                session.update_preferences('preferred_effects', effects['desired'])
            if effects.get('avoid'):
                session.update_preferences('avoid_effects', effects['avoid'])
        
        # Добавляем запись в историю разговора
        session.add_conversation_entry(
            query=query,
            response=analysis.response_text,
            intent=session.current_topic
        )
        
        # Обновляем время активности
        session.update_activity()
    
    def _build_optimized_response(
        self,
        analysis: UnifiedAnalysis,
        strains: List[Strain],
        session: ConversationSession
    ) -> ChatResponse:
        """Построение оптимизированного ответа"""
        
        # Используем уже сгенерированный текст из unified analysis
        response_text = analysis.response_text
        
        # Добавляем предупреждения о конфликтах
        if analysis.warnings:
            warning_text = f"\n⚠️ {', '.join(analysis.warnings)}"
            response_text += warning_text
        
        # Динамические quick actions
        quick_actions = self._generate_dynamic_quick_actions(
            strains, 
            analysis,
            session
        )
        
        # Компактные сорта для UI
        compact_strains = self._build_compact_strains(strains)
        
        return ChatResponse(
            response=response_text,
            recommended_strains=compact_strains,
            detected_intent=analysis.query_type,
            filters_applied=analysis.criteria or {},
            session_id=session.session_id,
            query_type=analysis.query_type,
            language=analysis.detected_language,
            confidence=analysis.confidence,
            quick_actions=quick_actions or analysis.suggested_quick_actions,
            is_restored=session.is_restored,
            is_fallback=analysis.is_fallback,
            warnings=analysis.warnings
        )
    
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
                feelings=[CompactFeeling(name=f.name) for f in strain.feelings],
                helps_with=[CompactHelpsWith(name=h.name) for h in strain.helps_with],
                negatives=[CompactNegative(name=n.name) for n in strain.negatives],
                flavors=[CompactFlavor(name=fl.name) for fl in strain.flavors]
            )
            compact_strains.append(compact_strain)
        
        return compact_strains
    
    def _build_strain_url(self, strain_slug: str) -> Optional[str]:
        """Построение URL для сорта"""
        if not strain_slug:
            return None
        base_url = os.getenv('CANNAMENTE_BASE_URL')
        url_pattern = os.getenv('STRAIN_URL_PATTERN', '/strain/{slug}/')
        return f"{base_url}{url_pattern.format(slug=strain_slug)}"
    
    def _generate_dynamic_quick_actions(
        self,
        strains: List[Strain],
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[str]:
        """Генерация контекстных quick actions"""
        
        actions = []
        lang = analysis.detected_language
        
        if len(strains) > 1:
            # Действия для множественного выбора
            if lang == 'es':
                actions.append(f"Comparar {strains[0].name} y {strains[1].name}")
                actions.append("Ver el más potente")
                actions.append("Ver el más suave")
            else:
                actions.append(f"Compare {strains[0].name} and {strains[1].name}")
                actions.append("Show strongest")
                actions.append("Show mildest")
        
        if strains and any(s.thc and float(s.thc) > 20 for s in strains):
            # Если есть сильные сорта
            action = "Ver opciones más suaves" if lang == 'es' else "Show milder options"
            actions.append(action)
        
        # Добавляем reset опцию если есть история
        if session.conversation_history:
            reset = "Empezar nueva búsqueda" if lang == 'es' else "Start new search"
            actions.append(reset)
        
        return actions[:4]  # Максимум 4 действия
    
    def _get_new_search_suggestions(self, language: str) -> List[str]:
        """Получить предложения для нового поиска"""
        
        if language == 'es':
            return ['Para dormir', 'Para energía', 'Para dolor', 'Para creatividad']
        else:
            return ['For sleep', 'For energy', 'For pain', 'For creativity']