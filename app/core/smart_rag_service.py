import logging
from typing import List, Optional, Dict, Any
from app.models.session import ConversationSession
from app.models.schemas import ChatResponse, CompactStrain, CompactFeeling, CompactHelpsWith, CompactNegative, CompactFlavor, Strain
from app.models.database import Strain as StrainModel  # For direct DB queries
from app.core.session_manager import get_session_manager
from app.db.repository import StrainRepository
from app.core.llm_interface import get_llm

# Streamlined RAG v4.0 Components
from app.core.streamlined_analyzer import StreamlinedQueryAnalyzer, QueryAnalysis
from app.core.category_filter import FilterFactory, FilterChain
from app.core.vector_search_service import VectorSearchService

import os

logger = logging.getLogger(__name__)


class SmartRAGService:
    """
    Streamlined RAG Service v4.0 - AI-powered Cannabis Strain Recommendation System

    Architecture:
    - LLM-based query analysis with intent detection
    - SQL pre-filtering (category, THC, CBD) with PostgreSQL fuzzy matching
    - Universal attribute filtering (flavors, effects, medical uses, terpenes)
    - Vector semantic search for ranking
    - Context-aware session management
    """

    def __init__(self, repository: StrainRepository):
        self.repository = repository
        self.session_manager = get_session_manager()

        # Initialize Streamlined RAG v4.0 components
        self.llm_interface = get_llm()
        self.streamlined_analyzer = StreamlinedQueryAnalyzer(self.llm_interface)
        self.vector_search = VectorSearchService(self.llm_interface, repository.db)
        self.filter_factory = FilterFactory()

        logger.info("🚀 Streamlined RAG v4.0 initialized")
    
    def process_contextual_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        history: Optional[List[str]] = None,
        source_platform: Optional[str] = None
    ) -> ChatResponse:
        """
        Main query processing method - Streamlined RAG v4.0

        Processes user queries through:
        1. LLM query analysis (intent, category, attributes)
        2. SQL pre-filtering with fuzzy matching
        3. Vector semantic search
        4. Context-aware response generation
        """

        logger.info(f"Processing query: {query[:50]}...")

        # Get or create session
        session = self.session_manager.get_or_restore_session(session_id)

        # Process with Streamlined RAG v4.0
        return self._streamlined_process_query(query, session)
    def _streamlined_process_query(
        self,
        query: str,
        session: ConversationSession
    ) -> ChatResponse:
        """
        Streamlined RAG v4.0 - Упрощённая обработка запросов

        Архитектура:
        1. Minimal LLM prompt: только category detection + natural response
        2. Simple SQL filter: только по категории (если детектирована)
        3. Vector search: основной метод поиска (batch-optimized)

        Преимущества:
        - Меньше токенов в промпте (~50 строк вместо 278)
        - Быстрее: batch vector search вместо N+1 queries
        - Проще: нет сложной генерации SQL фильтров
        - Расширяемо: легко добавить CBD/terpene фильтры
        """

        logger.info(f"🚀 Streamlined RAG v4.0: Processing query '{query[:50]}...'")

        # Получаем session context для анализа
        session_context = self._build_session_context(session)

        # Step 1: Minimal LLM analysis (category + natural response + follow-up detection)
        try:
            # Get session strains for context-aware analysis
            session_strains = self._get_session_strains(session)

            # Build context with previous strains
            analysis_context = session_context.copy()
            if session_strains:
                analysis_context['recommended_strains'] = [
                    f"{s.name} ({s.category}, THC: {s.thc}%)"
                    for s in session_strains[:5]
                ]
            else:
                analysis_context['recommended_strains'] = []

            logger.info(f"Context for LLM: strains={len(session_strains)}, recommended_strains={analysis_context['recommended_strains']}")

            analysis = self.streamlined_analyzer.analyze_query(
                user_query=query,
                session_context=analysis_context,
                found_strains=None  # Will be filled after search
            )
            logger.info(f"Analysis: category={analysis.detected_category}, is_follow_up={analysis.is_follow_up}, language={analysis.detected_language}")
        except Exception as e:
            logger.error(f"Streamlined analysis failed: {e}", exc_info=True)
            # Fallback to empty analysis
            analysis = QueryAnalysis(
                detected_category=None,
                thc_level=None,
                cbd_level=None,
                is_search_query=True,  # Default to search in fallback
                is_follow_up=False,
                natural_response="I can help you find the right strain.",
                suggested_follow_ups=[],
                detected_language=self._detect_language(query),
                confidence=0.5
            )

        # Step 2: Handle non-search queries (greetings, help requests, general questions)
        if not analysis.is_search_query:
            logger.info(f"❌ Non-search query detected - returning text-only response")

            # Update session with conversation but no strains
            self._update_session_streamlined(session, query, analysis, [])

            # Save session
            self.session_manager.save_session_with_backup(session)

            # Build response WITHOUT recommended_strains
            return self._build_streamlined_response(
                analysis,
                [],  # No strains for non-search queries
                session,
                filters_applied={"is_search_query": False, "reason": "greeting_or_general_question"}
            )

        # Step 3: Handle follow-up queries with session context (SIMPLE)
        if analysis.is_follow_up and session_strains:
            logger.info(f"🔄 Follow-up query detected - returning session strains")

            # Simply return session strains (LLM already answered in natural_response)
            result_strains = session_strains

            # Update session
            self._update_session_streamlined(session, query, analysis, result_strains)

            # Save session
            self.session_manager.save_session_with_backup(session)

            # Build response
            return self._build_streamlined_response(
                analysis,
                result_strains,
                session,
                filters_applied={"is_follow_up": True}
            )

        # Step 3: Build SQL filters (category + THC/CBD) for NEW search
        filter_params = {
            'is_search_query': True  # Log that this is a search query
        }

        # Category filter
        if analysis.detected_category:
            filter_params['category'] = analysis.detected_category

        # THC level → min/max конвертация
        if analysis.thc_level == "low":
            filter_params['max_thc'] = 10
        elif analysis.thc_level == "medium":
            filter_params['min_thc'] = 10
            filter_params['max_thc'] = 20
        elif analysis.thc_level == "high":
            filter_params['min_thc'] = 20

        # CBD level → min/max конвертация (по стандартам медицинских сортов)
        if analysis.cbd_level == "low":
            filter_params['max_cbd'] = 3
        elif analysis.cbd_level == "medium":
            filter_params['min_cbd'] = 3
            filter_params['max_cbd'] = 10
        elif analysis.cbd_level == "high":
            filter_params['min_cbd'] = 10

        # Create filter chain
        filter_chain = self.filter_factory.create_from_params(filter_params)
        logger.info(f"Filters: {filter_chain.get_filter_names()}")

        # Step 3: Apply SQL filters to get candidates
        base_query = self.repository.db.query(StrainModel)
        filtered_query = filter_chain.apply(base_query)
        candidates = filtered_query.all()

        logger.info(f"SQL filtering (category/THC/CBD): {len(candidates)} candidates")

        # Step 3.5: Apply attribute filters with PostgreSQL fuzzy matching
        if candidates and (analysis.required_flavors or analysis.required_effects or
                          analysis.required_helps_with or analysis.exclude_negatives or
                          analysis.required_terpenes):
            original_count = len(candidates)
            candidates = self._apply_attribute_filters(
                candidates,
                analysis,
                filter_params
            )
            logger.info(f"After attribute filtering: {len(candidates)} candidates (was {original_count})")

            # If attribute filtering removed ALL candidates, fall back to original set
            # This ensures we always have results even if exact match not found
            if not candidates:
                logger.warning("Attribute filters too strict - falling back to category/THC/CBD results")
                candidates = filtered_query.all()
                # Mark that we're showing approximate results
                filter_params['attribute_fallback'] = True

        # Track if fallback was used
        fallback_used = False

        # Step 4: Vector search (batch-optimized, primary search method)
        if candidates:
            try:
                result_strains = self.vector_search.search(
                    query=query,
                    candidates=candidates,
                    language=analysis.detected_language,
                    limit=5  # Return top 5 strains (like old system)
                )
                logger.info(f"Vector search: {len(result_strains)} results")
            except Exception as e:
                logger.error(f"Vector search failed: {e}", exc_info=True)
                # Fallback: return first N candidates
                result_strains = candidates[:5]
        else:
            # No candidates after filtering - smart fallback
            fallback_used = True

            # Если были THC/CBD фильтры, убрать их но сохранить категорию
            if analysis.thc_level or analysis.cbd_level:
                logger.warning("No candidates with THC/CBD filters, retrying with category only")
                fallback_params = {}
                if analysis.detected_category:
                    fallback_params['category'] = analysis.detected_category

                fallback_chain = self.filter_factory.create_from_params(fallback_params)
                fallback_query = fallback_chain.apply(base_query)
                candidates = fallback_query.all()
                logger.info(f"Fallback filtering (category only): {len(candidates)} candidates")

            # Если все еще 0 результатов, используем все active сорта
            if not candidates:
                logger.warning("No candidates even with category only, using all active strains")
                candidates = self.repository.db.query(StrainModel).filter(
                    StrainModel.active == True
                ).all()

            result_strains = self.vector_search.search(
                query=query,
                candidates=candidates,
                language=analysis.detected_language,
                limit=5
            )

        # Step 5: Re-analyze with found strains to improve natural response
        if result_strains:
            try:
                strain_info = [
                    {
                        'name': s.name,
                        'category': s.category,
                        'thc': str(s.thc) if s.thc else 'N/A'
                    }
                    for s in result_strains[:5]
                ]
                final_analysis = self.streamlined_analyzer.analyze_query(
                    user_query=query,
                    session_context=session_context,
                    found_strains=strain_info,
                    fallback_used=fallback_used  # Pass fallback info to LLM
                )
                analysis = final_analysis
            except Exception as e:
                logger.warning(f"Failed to re-analyze with strains: {e}")
                # Keep original analysis

        # Step 6: Add fallback notice if exact match not found
        if fallback_used and result_strains:
            if analysis.detected_language == 'es':
                notice = "ℹ️ No encontré coincidencias exactas. Aquí están las opciones más cercanas:\n\n"
            else:
                notice = "ℹ️ No exact matches found. Here are the closest options:\n\n"
            analysis.natural_response = notice + analysis.natural_response

        # Step 7: Update session
        self._update_session_streamlined(session, query, analysis, result_strains)

        # Step 8: Save session
        self.session_manager.save_session_with_backup(session)

        # Step 9: Build response
        return self._build_streamlined_response(analysis, result_strains, session, filter_params)

    def _apply_attribute_filters(
        self,
        candidates: List[StrainModel],
        analysis: QueryAnalysis,
        filter_params: Dict[str, Any]
    ) -> List[StrainModel]:
        """
        Apply attribute filters with PostgreSQL fuzzy matching (ILIKE)

        Handles: flavors, effects, helps_with, negatives, terpenes
        Uses ILIKE for case-insensitive partial matching (handles typos like 'tropicas' → 'tropical')

        Args:
            candidates: Pre-filtered strains from category/THC/CBD filters
            analysis: Query analysis with extracted attributes
            filter_params: Dict to store applied filters for logging

        Returns:
            Filtered list of strains matching attribute criteria
        """
        from app.models.database import Flavor, Feeling, HelpsWith, Negative, Terpene

        filtered = candidates
        candidate_ids = [s.id for s in filtered]

        # Filter by required flavors (fuzzy matching with ILIKE)
        if analysis.required_flavors:
            logger.info(f"Filtering by flavors: {analysis.required_flavors}")

            flavor_query = self.repository.db.query(StrainModel).join(
                StrainModel.flavors
            ).filter(
                StrainModel.id.in_(candidate_ids)
            )

            # Build OR conditions for fuzzy matching (EN + ES)
            flavor_conditions = []
            for flavor in analysis.required_flavors:
                # Используем первые 5 символов для fuzzy matching (handles typos)
                pattern = f"%{flavor[:5].lower()}%"
                flavor_conditions.append(
                    (Flavor.name_en.ilike(pattern)) | (Flavor.name_es.ilike(pattern))
                )

            # Apply OR logic: any flavor matches
            if flavor_conditions:
                from sqlalchemy import or_
                flavor_query = flavor_query.filter(or_(*flavor_conditions))
                filtered = flavor_query.distinct().all()
                candidate_ids = [s.id for s in filtered]
                filter_params['flavors'] = analysis.required_flavors
                logger.info(f"After flavor filter: {len(filtered)} strains")

        # Filter by required effects (feelings)
        if analysis.required_effects and filtered:
            logger.info(f"Filtering by effects: {analysis.required_effects}")

            effects_query = self.repository.db.query(StrainModel).join(
                StrainModel.feelings
            ).filter(
                StrainModel.id.in_(candidate_ids)
            )

            effect_conditions = []
            for effect in analysis.required_effects:
                pattern = f"%{effect[:5].lower()}%"
                effect_conditions.append(
                    (Feeling.name_en.ilike(pattern)) | (Feeling.name_es.ilike(pattern))
                )

            if effect_conditions:
                from sqlalchemy import or_
                effects_query = effects_query.filter(or_(*effect_conditions))
                filtered = effects_query.distinct().all()
                candidate_ids = [s.id for s in filtered]
                filter_params['effects'] = analysis.required_effects
                logger.info(f"After effects filter: {len(filtered)} strains")

        # Filter by medical uses (helps_with)
        if analysis.required_helps_with and filtered:
            logger.info(f"Filtering by helps_with: {analysis.required_helps_with}")

            helps_query = self.repository.db.query(StrainModel).join(
                StrainModel.helps_with
            ).filter(
                StrainModel.id.in_(candidate_ids)
            )

            helps_conditions = []
            for condition in analysis.required_helps_with:
                pattern = f"%{condition[:5].lower()}%"
                helps_conditions.append(
                    (HelpsWith.name_en.ilike(pattern)) | (HelpsWith.name_es.ilike(pattern))
                )

            if helps_conditions:
                from sqlalchemy import or_
                helps_query = helps_query.filter(or_(*helps_conditions))
                filtered = helps_query.distinct().all()
                candidate_ids = [s.id for s in filtered]
                filter_params['helps_with'] = analysis.required_helps_with
                logger.info(f"After helps_with filter: {len(filtered)} strains")

        # Exclude strains with unwanted side effects
        if analysis.exclude_negatives and filtered:
            logger.info(f"Excluding negatives: {analysis.exclude_negatives}")

            # Get strain IDs that have any of the excluded negatives
            negatives_query = self.repository.db.query(StrainModel.id).join(
                StrainModel.negatives
            ).filter(
                StrainModel.id.in_(candidate_ids)
            )

            negative_conditions = []
            for negative in analysis.exclude_negatives:
                pattern = f"%{negative[:5].lower()}%"
                negative_conditions.append(
                    (Negative.name_en.ilike(pattern)) | (Negative.name_es.ilike(pattern))
                )

            if negative_conditions:
                from sqlalchemy import or_
                negatives_query = negatives_query.filter(or_(*negative_conditions))
                exclude_ids = [row[0] for row in negatives_query.distinct().all()]

                # Filter out strains with excluded negatives
                filtered = [s for s in filtered if s.id not in exclude_ids]
                candidate_ids = [s.id for s in filtered]
                filter_params['exclude_negatives'] = analysis.exclude_negatives
                logger.info(f"After excluding negatives: {len(filtered)} strains")

        # Filter by terpenes (exact scientific names)
        if analysis.required_terpenes and filtered:
            logger.info(f"Filtering by terpenes: {analysis.required_terpenes}")

            terpenes_query = self.repository.db.query(StrainModel).join(
                StrainModel.terpenes
            ).filter(
                StrainModel.id.in_(candidate_ids)
            )

            terpene_conditions = []
            for terpene in analysis.required_terpenes:
                pattern = f"%{terpene[:5].lower()}%"
                terpene_conditions.append(Terpene.name.ilike(pattern))

            if terpene_conditions:
                from sqlalchemy import or_
                terpenes_query = terpenes_query.filter(or_(*terpene_conditions))
                filtered = terpenes_query.distinct().all()
                filter_params['terpenes'] = analysis.required_terpenes
                logger.info(f"After terpenes filter: {len(filtered)} strains")

        return filtered

    def _build_session_context(self, session: ConversationSession) -> Dict[str, Any]:
        """Build minimal session context for streamlined analyzer"""

        context = {
            'detected_language': session.detected_language or 'es',
            'conversation_history': []
        }

        # Add recent conversation history
        if session.conversation_history:
            context['conversation_history'] = [
                {
                    'query': entry.get('query', ''),
                    'response': entry.get('response', '')[:100]  # Truncate
                }
                for entry in session.conversation_history[-3:]  # Last 3 entries
            ]

        return context

    def _get_session_strains(self, session: ConversationSession) -> List[Strain]:
        """Get strains from most recent session recommendation"""

        # Use built-in method from session model
        strain_ids = session.get_last_strains()

        if not strain_ids:
            return []

        # Fetch strains from database
        try:
            strains = self.repository.db.query(StrainModel).filter(
                StrainModel.id.in_(strain_ids)
            ).all()

            # Sort strains to match original order
            strain_dict = {s.id: s for s in strains}
            ordered_strains = [strain_dict[sid] for sid in strain_ids if sid in strain_dict]

            logger.info(f"Retrieved {len(ordered_strains)} session strains")
            return ordered_strains

        except Exception as e:
            logger.error(f"Failed to retrieve session strains: {e}")
            return []

    def _update_session_streamlined(
        self,
        session: ConversationSession,
        query: str,
        analysis: QueryAnalysis,
        strains: List[Strain]
    ):
        """Update session after streamlined processing"""

        # Update language
        if analysis.detected_language:
            session.detected_language = analysis.detected_language

        # Add strains to history
        if strains:
            strain_ids = [s.id for s in strains]
            session.add_strain_recommendation(strain_ids)
            logger.info(f"Added {len(strain_ids)} strains to session history")

        # Add conversation entry
        session.add_conversation_entry(
            query=query,
            response=analysis.natural_response,
            intent=analysis.detected_category or 'search'
        )

        # Update activity
        session.update_activity()

    def _build_streamlined_response(
        self,
        analysis: QueryAnalysis,
        strains: List[Strain],
        session: ConversationSession,
        filters_applied: Dict[str, Any]
    ) -> ChatResponse:
        """Build response for streamlined processing"""

        # Substitute placeholders with real strain names
        response_text = self._substitute_strain_placeholders(analysis.natural_response, strains)

        # Build compact strains
        compact_strains = self._build_compact_strains(strains)

        # Quick actions
        quick_actions = analysis.suggested_follow_ups or self._generate_contextual_actions(
            strains, analysis.detected_language, session
        )

        return ChatResponse(
            response=response_text,
            recommended_strains=compact_strains,
            detected_intent=analysis.detected_category or 'search',
            filters_applied=filters_applied,
            session_id=session.session_id,
            query_type='streamlined_search',
            language=analysis.detected_language,
            confidence=analysis.confidence,
            quick_actions=quick_actions,
            is_restored=session.is_restored,
            is_fallback=False
        )

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
                url=self._build_strain_url(strain.slug or ""),
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
    
    def _build_strain_url(self, strain_slug: Optional[str]) -> Optional[str]:
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
    
