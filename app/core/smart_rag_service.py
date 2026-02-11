import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
from app.models.session import ConversationSession
from app.models.schemas import (
    ChatResponse,
    CompactStrain,
    CompactFeeling,
    CompactHelpsWith,
    CompactNegative,
    CompactFlavor,
    CompactTerpene,
    Strain,
)
from app.models.database import Strain as StrainModel  # For direct DB queries
from app.core.session_manager import get_session_manager
from app.db.repository import StrainRepository
from app.core.llm_interface import get_llm

# Streamlined RAG v4.0 Components
from app.core.streamlined_analyzer import StreamlinedQueryAnalyzer, QueryAnalysis, FollowUpIntent
from app.core.category_filter import FilterFactory, FilterChain
from app.core.vector_search_service import VectorSearchService

# Deterministic Follow-up Executor (FIX-001)
from app.core.follow_up_executor import FollowUpExecutor, detect_follow_up_intent_keywords

# DB-Aware Architecture - Taxonomy System
from app.core.taxonomy_init import get_taxonomy_system

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

    def __init__(self, repository: Optional[StrainRepository] = None):
        self.repository = repository
        self.session_manager = get_session_manager()

        # When repository is None this instance is used only as an async
        # entry-point (aprocess_contextual_query).  The real DB-bound instance
        # is created inside _init_db on the dedicated DB thread.
        if repository is None:
            self.llm_interface = None
            self.streamlined_analyzer = None
            self.fuzzy_matcher = None
            self.vector_search = None
            self.filter_factory = None
            self.follow_up_executor = None
            return

        # Initialize Streamlined RAG v4.0 components
        self.llm_interface = get_llm()

        # Get ContextBuilder and FuzzyMatcher from taxonomy system (DB-Aware Architecture)
        context_builder = None
        fuzzy_matcher = None
        taxonomy_system = get_taxonomy_system()
        if taxonomy_system:
            context_builder = taxonomy_system.context_builder
            fuzzy_matcher = taxonomy_system.fuzzy_matcher
            logger.info("✅ Using ContextBuilder and FuzzyMatcher with DB taxonomy")
        else:
            logger.warning("⚠️ Taxonomy system not initialized - using hardcoded taxonomy and ILIKE fallback")

        self.streamlined_analyzer = StreamlinedQueryAnalyzer(
            self.llm_interface,
            context_builder=context_builder
        )
        self.fuzzy_matcher = fuzzy_matcher
        self.vector_search = VectorSearchService(self.llm_interface, repository.db)
        self.filter_factory = FilterFactory()

        # FIX-001: Deterministic follow-up executor (eliminates hallucinations)
        self.follow_up_executor = FollowUpExecutor()

        logger.info("🚀 Streamlined RAG v4.0 initialized with deterministic follow-up executor")
    
    def process_contextual_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        language: Optional[str] = None,
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

        # Distributed lock prevents race conditions on concurrent same-session requests
        with self.session_manager.session_lock(session_id):
            # Get or create session
            session = self.session_manager.get_or_restore_session(session_id)

            # Process with Streamlined RAG v4.0
            return self._streamlined_process_query(query, session, language)

    async def aprocess_contextual_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        language: Optional[str] = None,
        history: Optional[List[str]] = None,
        source_platform: Optional[str] = None
    ) -> ChatResponse:
        """
        Async entry point for query processing.

        Granular async pipeline:
        - LLM calls run as native async (no thread needed)
        - DB calls run in a dedicated single-thread executor (thread safety)
        - Redis session ops run as native async
        """
        logger.info(f"Async processing query: {query[:50]}...")

        async with self.session_manager.async_session_lock(session_id):
            # Async session management (native async Redis)
            session = await self.session_manager.aget_or_restore_session(session_id)

            loop = asyncio.get_event_loop()
            db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-req")
            db_ref = [None]

            def _init_db():
                from app.db.database import SessionLocal
                db = SessionLocal()
                db_ref[0] = db
                repo = StrainRepository(db)
                return SmartRAGService(repo)

            db_svc = await loop.run_in_executor(db_executor, _init_db)

            try:
                return await self._async_streamlined_process_query(
                    query, session, language, db_svc, db_executor
                )
            finally:
                if db_ref[0]:
                    await loop.run_in_executor(db_executor, db_ref[0].close)
                db_executor.shutdown(wait=False)

    async def _async_streamlined_process_query(
        self,
        query: str,
        session: ConversationSession,
        explicit_language: Optional[str],
        db_svc: 'SmartRAGService',
        db_executor: ThreadPoolExecutor,
    ) -> ChatResponse:
        """
        Async version of _streamlined_process_query.

        Same branching logic, but:
        - LLM calls are native async (aanalyze_query, agenerate_response_only, agenerate_embedding)
        - DB calls go through run_in_executor(db_executor) for thread safety
        - Session save is native async Redis
        """
        loop = asyncio.get_event_loop()

        def run_db(fn, *args):
            return loop.run_in_executor(db_executor, fn, *args)

        logger.info(f"🚀 Async Streamlined RAG v4.0: Processing query '{query[:50]}...'")

        # --- Setup (CPU only) ---
        detected_language = db_svc._determine_language(explicit_language, session)
        logger.info(f"Language determined: {detected_language} (explicit: {explicit_language}, session: {session.detected_language})")

        session_context = db_svc._build_session_context(session)

        # DB: get session strains for context
        session_strains = await run_db(db_svc._get_session_strains, session)

        # Build analysis context (CPU)
        analysis_context = session_context.copy()
        if session_strains:
            analysis_context['recommended_strains'] = [
                f"{s.name} ({s.category}, THC: {s.thc}%)"
                for s in session_strains[:5]
            ]
        else:
            analysis_context['recommended_strains'] = []

        logger.info(f"Context for LLM: strains={len(session_strains)}, recommended_strains={analysis_context['recommended_strains']}")

        # --- ASYNC LLM: Analysis (~1-2s, no thread) ---
        try:
            analysis = await db_svc.streamlined_analyzer.aanalyze_query(
                user_query=query,
                session_context=analysis_context,
                found_strains=None,
                explicit_language=detected_language
            )
            logger.info(f"Analysis: category={analysis.detected_category}, is_follow_up={analysis.is_follow_up}, language={analysis.detected_language}")
        except Exception as e:
            logger.error(f"Async streamlined analysis failed: {e}", exc_info=True)
            analysis = QueryAnalysis(
                detected_category=None,
                thc_level=None,
                cbd_level=None,
                is_search_query=True,
                is_follow_up=False,
                natural_response="I can help you find the right strain.",
                suggested_follow_ups=[],
                detected_language=detected_language,
                confidence=0.5
            )

        # --- Branch: non-search ---
        if not analysis.is_search_query:
            logger.info("❌ Non-search query detected - returning text-only response")
            db_svc._update_session_streamlined(session, query, analysis, [])
            await self.session_manager.asave_session_with_backup(session)
            return await run_db(
                db_svc._build_streamlined_response,
                analysis, [], session,
                {"is_search_query": False, "reason": "greeting_or_general_question"}
            )

        # --- Branch: follow-up (deterministic, CPU + DB for response building) ---
        if analysis.is_follow_up and session_strains:
            logger.info("🔄 Follow-up query detected - using deterministic executor")
            intent = analysis.follow_up_intent
            if not intent:
                logger.info("No follow_up_intent from LLM, using keyword detection")
                intent = detect_follow_up_intent_keywords(query)

            result_strains, deterministic_response = db_svc.follow_up_executor.execute(
                intent=intent,
                session_strains=session_strains,
                language=analysis.detected_language
            )
            analysis.natural_response = deterministic_response
            db_svc._update_session_streamlined(session, query, analysis, result_strains)
            await self.session_manager.asave_session_with_backup(session)
            return await run_db(
                db_svc._build_streamlined_response,
                analysis, result_strains, session,
                {"is_follow_up": True, "deterministic_executor": True}
            )

        # --- Branch: specific strain (DB + async embedding fallback) ---
        if analysis.specific_strain_name:
            logger.info(f"🎯 Specific strain query detected: '{analysis.specific_strain_name}'")

            def _find_specific_strain():
                specific_strain = db_svc.repository.db.query(StrainModel).filter(
                    StrainModel.name.ilike(analysis.specific_strain_name),
                    StrainModel.active == True
                ).first()
                if specific_strain:
                    logger.info(f"✅ Found specific strain: {specific_strain.name}")
                    return [specific_strain], False
                else:
                    logger.warning(f"❌ Specific strain '{analysis.specific_strain_name}' not found - searching closest match")
                    all_strains = db_svc.repository.db.query(StrainModel).filter(
                        StrainModel.active == True
                    ).all()
                    return all_strains, True  # need vector search fallback

            found_strains, needs_vector_search = await run_db(_find_specific_strain)

            if needs_vector_search and found_strains:
                # Async embedding (no thread) + DB distance calc (thread)
                query_emb = await db_svc.vector_search.llm.agenerate_embedding(analysis.specific_strain_name)
                result_strains = await run_db(
                    db_svc.vector_search._search_with_embedding,
                    query_emb, found_strains, analysis.detected_language, 1
                )
            else:
                result_strains = found_strains
            db_svc._update_session_streamlined(session, query, analysis, result_strains)
            await self.session_manager.asave_session_with_backup(session)
            return await run_db(
                db_svc._build_streamlined_response,
                analysis, result_strains, session,
                {"specific_strain_query": True, "strain_name": analysis.specific_strain_name}
            )

        # --- Main search path ---

        # DB: Build filters + apply + attribute filtering
        def _db_filter_phase():
            filter_params = {'is_search_query': True}

            if analysis.detected_category:
                filter_params['category'] = analysis.detected_category

            if analysis.thc_level == "low":
                filter_params['max_thc'] = 10
            elif analysis.thc_level == "medium":
                filter_params['min_thc'] = 10
                filter_params['max_thc'] = 20
            elif analysis.thc_level == "high":
                filter_params['min_thc'] = 20

            if analysis.cbd_level == "low":
                filter_params['max_cbd'] = 3
            elif analysis.cbd_level == "medium":
                filter_params['min_cbd'] = 3
                filter_params['max_cbd'] = 10
            elif analysis.cbd_level == "high":
                filter_params['min_cbd'] = 7

            filter_chain = db_svc.filter_factory.create_from_params(filter_params)
            logger.info(f"Filters: {filter_chain.get_filter_names()}")

            base_query = db_svc.repository.db.query(StrainModel)
            filtered_query = filter_chain.apply(base_query)
            candidates = filtered_query.all()

            logger.info(f"SQL filtering (category/THC/CBD): {len(candidates)} candidates")

            if candidates and (analysis.required_flavors or analysis.required_effects or
                              analysis.required_helps_with or analysis.exclude_negatives or
                              analysis.required_terpenes):
                original_count = len(candidates)
                candidates = db_svc._apply_attribute_filters(candidates, analysis, filter_params)
                logger.info(f"After attribute filtering: {len(candidates)} candidates (was {original_count})")

                if not candidates:
                    logger.warning("Attribute filters too strict - falling back to category/THC/CBD results")
                    candidates = filtered_query.all()
                    filter_params['attribute_fallback'] = True

            return candidates, filter_params

        candidates, filter_params = await run_db(_db_filter_phase)

        # Handle no-candidates fallback (DB)
        fallback_used = False
        if not candidates:
            fallback_used = True

            def _fallback_candidates():
                nonlocal candidates
                if analysis.thc_level or analysis.cbd_level:
                    logger.warning("No candidates with THC/CBD filters, retrying with category only")
                    fallback_params = {}
                    if analysis.detected_category:
                        fallback_params['category'] = analysis.detected_category
                    fallback_chain = db_svc.filter_factory.create_from_params(fallback_params)
                    base_q = db_svc.repository.db.query(StrainModel)
                    fb_candidates = fallback_chain.apply(base_q).all()
                    logger.info(f"Fallback filtering (category only): {len(fb_candidates)} candidates")
                    if fb_candidates:
                        return fb_candidates

                logger.warning("No candidates even with category only, using all active strains")
                return db_svc.repository.db.query(StrainModel).filter(
                    StrainModel.active == True
                ).all()

            candidates = await run_db(_fallback_candidates)

        # ASYNC: Vector search — async embedding + DB distance calculation
        if candidates:
            try:
                # Async LLM embedding (no thread needed)
                query_embedding = await db_svc.vector_search.llm.agenerate_embedding(query)
                if not query_embedding or len(query_embedding) == 0:
                    raise ValueError("Empty embedding received from LLM")
                # DB: batch cosine distance (in dedicated thread)
                result_strains = await run_db(
                    db_svc.vector_search._search_with_embedding,
                    query_embedding, candidates, analysis.detected_language, 5
                )
                logger.info(f"Vector search: {len(result_strains)} results")
            except Exception as e:
                logger.error(f"Async vector search failed: {e}", exc_info=True)
                result_strains = candidates[:5]
        else:
            result_strains = []

        # ASYNC LLM: Response generation (~0.5-1s, no thread)
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
                improved_response = await db_svc.streamlined_analyzer.agenerate_response_only(
                    query=query,
                    strains=strain_info,
                    language=detected_language
                )
                analysis.natural_response = improved_response
            except Exception as e:
                logger.warning(f"Async mini-prompt re-analysis failed: {e}")

        # Fallback notice
        if fallback_used and result_strains:
            if analysis.detected_language == 'es':
                notice = "ℹ️ No encontré coincidencias exactas. Aquí están las opciones más cercanas:\n\n"
            else:
                notice = "ℹ️ No exact matches found. Here are the closest options:\n\n"
            analysis.natural_response = notice + analysis.natural_response

        # Update session (CPU)
        db_svc._update_session_streamlined(session, query, analysis, result_strains)

        # ASYNC: Session save (Redis)
        await self.session_manager.asave_session_with_backup(session)

        # DB: Build response (needs DB for lazy-loaded relationships)
        return await run_db(
            db_svc._build_streamlined_response,
            analysis, result_strains, session, filter_params
        )

    def _streamlined_process_query(
        self,
        query: str,
        session: ConversationSession,
        explicit_language: Optional[str] = None
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

        # Determine language with priority: explicit > session > default
        detected_language = self._determine_language(explicit_language, session)
        logger.info(f"Language determined: {detected_language} (explicit: {explicit_language}, session: {session.detected_language})")

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
                found_strains=None,  # Will be filled after search
                explicit_language=detected_language
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
                detected_language=detected_language,
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

        # Step 3: Handle follow-up queries with DETERMINISTIC executor (FIX-001)
        if analysis.is_follow_up and session_strains:
            logger.info(f"🔄 Follow-up query detected - using deterministic executor")

            # Get follow_up_intent from LLM analysis or detect via keywords
            intent = analysis.follow_up_intent
            if not intent:
                # Fallback: detect intent from query keywords
                logger.info("No follow_up_intent from LLM, using keyword detection")
                intent = detect_follow_up_intent_keywords(query)

            # Execute deterministically - NO LLM HALLUCINATION POSSIBLE
            result_strains, deterministic_response = self.follow_up_executor.execute(
                intent=intent,
                session_strains=session_strains,
                language=analysis.detected_language
            )

            # Override LLM response with deterministic response
            analysis.natural_response = deterministic_response

            # Update session
            self._update_session_streamlined(session, query, analysis, result_strains)

            # Save session
            self.session_manager.save_session_with_backup(session)

            # Build response
            return self._build_streamlined_response(
                analysis,
                result_strains,
                session,
                filters_applied={"is_follow_up": True, "deterministic_executor": True}
            )

        # Step 2.5: Handle SPECIFIC STRAIN queries (return only 1 strain, not 5 similar)
        if analysis.specific_strain_name:
            logger.info(f"🎯 Specific strain query detected: '{analysis.specific_strain_name}'")

            # Search for strain by exact name (case-insensitive)
            specific_strain = self.repository.db.query(StrainModel).filter(
                StrainModel.name.ilike(analysis.specific_strain_name),
                StrainModel.active == True
            ).first()

            if specific_strain:
                result_strains = [specific_strain]
                logger.info(f"✅ Found specific strain: {specific_strain.name}")
            else:
                # Strain not found - use vector search with limit=1 to find closest match
                logger.warning(f"❌ Specific strain '{analysis.specific_strain_name}' not found - searching closest match")
                all_strains = self.repository.db.query(StrainModel).filter(
                    StrainModel.active == True
                ).all()
                result_strains = self.vector_search.search(
                    query=analysis.specific_strain_name,
                    candidates=all_strains,
                    language=analysis.detected_language,
                    limit=1  # Only 1 strain for specific queries
                )

            # Update session
            self._update_session_streamlined(session, query, analysis, result_strains)

            # Save session
            self.session_manager.save_session_with_backup(session)

            # Build response
            return self._build_streamlined_response(
                analysis,
                result_strains,
                session,
                filters_applied={"specific_strain_query": True, "strain_name": analysis.specific_strain_name}
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
            filter_params['min_cbd'] = 7  # Lowered from 10 to include strains like Harlequin (9% CBD)

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

        # Step 5: FIX-003 - Use mini-prompt for re-analysis (10x smaller, 3-4x faster)
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
                # Use mini-prompt instead of full analysis
                improved_response = self.streamlined_analyzer.generate_response_only(
                    query=query,
                    strains=strain_info,
                    language=detected_language
                )
                analysis.natural_response = improved_response
            except Exception as e:
                logger.warning(f"Mini-prompt re-analysis failed: {e}")
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

    def _resolve_to_db_values(
        self,
        user_inputs: List[str],
        taxonomy_field: str,
        language: str = "es"
    ) -> List[str]:
        """
        Resolve user inputs to actual DB values using fuzzy matching

        Args:
            user_inputs: User's input values (may have typos or variations)
            taxonomy_field: Field name (flavors, feelings, helps_with, negatives, terpenes)
            language: Language for matching ("en" or "es")

        Returns:
            List of matched DB values

        Example:
            ["mint", "tropicas"] → ["menthol", "tropical"] (using trigram similarity)
        """
        if not user_inputs:
            return []

        if not self.fuzzy_matcher:
            # Fallback: return inputs as-is (ILIKE will be used)
            logger.debug(f"FuzzyMatcher not available - using inputs as-is for {taxonomy_field}")
            return user_inputs

        # Get taxonomy cache to get all possible DB values
        taxonomy_system = get_taxonomy_system()
        if not taxonomy_system:
            return user_inputs

        taxonomy = taxonomy_system.cache.get_taxonomy(language)
        db_candidates = taxonomy.get(taxonomy_field, [])

        if not db_candidates:
            logger.warning(f"No DB candidates for {taxonomy_field}")
            return user_inputs

        # Use fuzzy matcher to resolve each user input
        resolved = []
        for user_input in user_inputs:
            matches = self.fuzzy_matcher.match(
                user_input=user_input,
                candidates=db_candidates,
                threshold=0.3
            )

            if matches:
                # Take top match
                best_match = matches[0]
                resolved.append(best_match.matched_value)
                logger.debug(
                    f"Fuzzy match: '{user_input}' → '{best_match.matched_value}' "
                    f"(score: {best_match.score:.2f}, strategy: {best_match.strategy})"
                )
            else:
                # No match found - keep original (will try ILIKE fallback)
                resolved.append(user_input)
                logger.debug(f"No fuzzy match for '{user_input}' - using original")

        return resolved

    def _apply_attribute_filters(
        self,
        candidates: List[StrainModel],
        analysis: QueryAnalysis,
        filter_params: Dict[str, Any]
    ) -> List[StrainModel]:
        """
        Apply attribute filters with PostgreSQL trigram fuzzy matching

        Handles: flavors, effects, helps_with, negatives, terpenes
        Uses FuzzyMatcher (trigram similarity) for better matching:
        - "mint" → "menthol" (similarity: 0.42)
        - "lemon" → "limonene" (similarity: 0.53)
        Falls back to ILIKE if fuzzy matcher not available

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

        # Detect language from analysis
        language = analysis.detected_language

        # Filter by required flavors (trigram fuzzy matching)
        if analysis.required_flavors:
            logger.info(f"Filtering by flavors (user input): {analysis.required_flavors}")

            # Resolve user inputs to DB values using fuzzy matching
            resolved_flavors = self._resolve_to_db_values(
                user_inputs=analysis.required_flavors,
                taxonomy_field="flavors",
                language=language
            )
            logger.info(f"Resolved flavors (DB values): {resolved_flavors}")

            if resolved_flavors:
                flavor_query = self.repository.db.query(StrainModel).join(
                    StrainModel.flavors
                ).filter(
                    StrainModel.id.in_(candidate_ids)
                )

                # Build OR conditions for exact/ILIKE matching after fuzzy resolution
                flavor_conditions = []
                for flavor in resolved_flavors:
                    # Try exact match first, then ILIKE fallback
                    flavor_conditions.append(
                        (Flavor.name_en.ilike(f"%{flavor.lower()}%")) |
                        (Flavor.name_es.ilike(f"%{flavor.lower()}%")) |
                        (Flavor.name.ilike(f"%{flavor.lower()}%"))
                    )

                # Apply OR logic: any flavor matches
                if flavor_conditions:
                    from sqlalchemy import or_
                    flavor_query = flavor_query.filter(or_(*flavor_conditions))
                    filtered = flavor_query.distinct().all()
                    candidate_ids = [s.id for s in filtered]
                    filter_params['flavors'] = resolved_flavors
                    logger.info(f"After flavor filter: {len(filtered)} strains")

        # Filter by required effects (feelings) - trigram fuzzy matching
        if analysis.required_effects and filtered:
            logger.info(f"Filtering by effects (user input): {analysis.required_effects}")

            # Resolve user inputs to DB values using fuzzy matching
            resolved_effects = self._resolve_to_db_values(
                user_inputs=analysis.required_effects,
                taxonomy_field="feelings",
                language=language
            )
            logger.info(f"Resolved effects (DB values): {resolved_effects}")

            if resolved_effects:
                effects_query = self.repository.db.query(StrainModel).join(
                    StrainModel.feelings
                ).filter(
                    StrainModel.id.in_(candidate_ids)
                )

                effect_conditions = []
                for effect in resolved_effects:
                    effect_conditions.append(
                        (Feeling.name_en.ilike(f"%{effect.lower()}%")) |
                        (Feeling.name_es.ilike(f"%{effect.lower()}%")) |
                        (Feeling.name.ilike(f"%{effect.lower()}%"))
                    )

                if effect_conditions:
                    from sqlalchemy import or_
                    effects_query = effects_query.filter(or_(*effect_conditions))
                    filtered = effects_query.distinct().all()
                    candidate_ids = [s.id for s in filtered]
                    filter_params['effects'] = resolved_effects
                    logger.info(f"After effects filter: {len(filtered)} strains")

        # Filter by medical uses (helps_with) - trigram fuzzy matching
        if analysis.required_helps_with and filtered:
            logger.info(f"Filtering by helps_with (user input): {analysis.required_helps_with}")

            # Resolve user inputs to DB values using fuzzy matching
            resolved_helps = self._resolve_to_db_values(
                user_inputs=analysis.required_helps_with,
                taxonomy_field="helps_with",
                language=language
            )
            logger.info(f"Resolved helps_with (DB values): {resolved_helps}")

            if resolved_helps:
                helps_query = self.repository.db.query(StrainModel).join(
                    StrainModel.helps_with
                ).filter(
                    StrainModel.id.in_(candidate_ids)
                )

                helps_conditions = []
                for condition in resolved_helps:
                    helps_conditions.append(
                        (HelpsWith.name_en.ilike(f"%{condition.lower()}%")) |
                        (HelpsWith.name_es.ilike(f"%{condition.lower()}%")) |
                        (HelpsWith.name.ilike(f"%{condition.lower()}%"))
                    )

                if helps_conditions:
                    from sqlalchemy import or_
                    helps_query = helps_query.filter(or_(*helps_conditions))
                    filtered = helps_query.distinct().all()
                    candidate_ids = [s.id for s in filtered]
                    filter_params['helps_with'] = resolved_helps
                    logger.info(f"After helps_with filter: {len(filtered)} strains")

        # Exclude strains with unwanted side effects - trigram fuzzy matching
        if analysis.exclude_negatives and filtered:
            logger.info(f"Excluding negatives (user input): {analysis.exclude_negatives}")

            # Resolve user inputs to DB values using fuzzy matching
            resolved_negatives = self._resolve_to_db_values(
                user_inputs=analysis.exclude_negatives,
                taxonomy_field="negatives",
                language=language
            )
            logger.info(f"Resolved negatives (DB values): {resolved_negatives}")

            if resolved_negatives:
                # Get strain IDs that have any of the excluded negatives
                negatives_query = self.repository.db.query(StrainModel.id).join(
                    StrainModel.negatives
                ).filter(
                    StrainModel.id.in_(candidate_ids)
                )

                negative_conditions = []
                for negative in resolved_negatives:
                    negative_conditions.append(
                        (Negative.name_en.ilike(f"%{negative.lower()}%")) |
                        (Negative.name_es.ilike(f"%{negative.lower()}%")) |
                        (Negative.name.ilike(f"%{negative.lower()}%"))
                    )

                if negative_conditions:
                    from sqlalchemy import or_
                    negatives_query = negatives_query.filter(or_(*negative_conditions))
                    exclude_ids = [row[0] for row in negatives_query.distinct().all()]

                    # Filter out strains with excluded negatives
                    filtered = [s for s in filtered if s.id not in exclude_ids]
                    candidate_ids = [s.id for s in filtered]
                    filter_params['exclude_negatives'] = resolved_negatives
                    logger.info(f"After excluding negatives: {len(filtered)} strains")

        # Filter by terpenes (scientific names) - trigram fuzzy matching
        if analysis.required_terpenes and filtered:
            logger.info(f"Filtering by terpenes (user input): {analysis.required_terpenes}")

            # Resolve user inputs to DB values using fuzzy matching
            resolved_terpenes = self._resolve_to_db_values(
                user_inputs=analysis.required_terpenes,
                taxonomy_field="terpenes",
                language=language
            )
            logger.info(f"Resolved terpenes (DB values): {resolved_terpenes}")

            if resolved_terpenes:
                terpenes_query = self.repository.db.query(StrainModel).join(
                    StrainModel.terpenes
                ).filter(
                    StrainModel.id.in_(candidate_ids)
                )

                terpene_conditions = []
                for terpene in resolved_terpenes:
                    terpene_conditions.append(Terpene.name.ilike(f"%{terpene.lower()}%"))

                if terpene_conditions:
                    from sqlalchemy import or_
                    terpenes_query = terpenes_query.filter(or_(*terpene_conditions))
                    filtered = terpenes_query.distinct().all()
                    candidate_ids = [s.id for s in filtered]
                    filter_params['terpenes'] = resolved_terpenes
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
        compact_strains = self._build_compact_strains(strains, language=analysis.detected_language)

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

    def _build_compact_strains(self, strains: List[Strain], language: Optional[str] = None) -> List[CompactStrain]:
        """Создание компактных объектов сортов для UI (с учётом языка EN/ES)"""

        lang = language if language in ("en", "es") else "en"

        def localized_taxonomy_name(obj: Any) -> Optional[str]:
            """
            Taxonomy models (Feeling/Flavor/HelpsWith/Negative) имеют поля name/name_en/name_es.
            Для UI возвращаем name в нужной локали, иначе fallback на доступное значение.
            """
            if obj is None:
                return None
            if lang == "es":
                return getattr(obj, "name_es", None) or getattr(obj, "name_en", None) or getattr(obj, "name", None)
            return getattr(obj, "name_en", None) or getattr(obj, "name_es", None) or getattr(obj, "name", None)
        
        compact_strains = []
        for strain in strains:
            # Очистка имени
            clean_name = strain.name.split(' | ')[0] if strain.name else strain.name

            feelings = []
            for f in (strain.feelings or []):
                feeling_name = localized_taxonomy_name(f)
                if feeling_name:
                    feelings.append(CompactFeeling(name=feeling_name))

            helps_with = []
            for h in (strain.helps_with or []):
                helps_name = localized_taxonomy_name(h)
                if helps_name:
                    helps_with.append(CompactHelpsWith(name=helps_name))

            negatives = []
            for n in (strain.negatives or []):
                negative_name = localized_taxonomy_name(n)
                if negative_name:
                    negatives.append(CompactNegative(name=negative_name))

            flavors = []
            for fl in (strain.flavors or []):
                flavor_name = localized_taxonomy_name(fl)
                if flavor_name:
                    flavors.append(CompactFlavor(name=flavor_name))
            
            compact_strain = CompactStrain(
                id=strain.id,
                name=clean_name,
                cbd=strain.cbd,
                thc=strain.thc,
                cbg=strain.cbg,
                category=strain.category,
                slug=strain.slug,
                url=self._build_strain_url(strain.slug or ""),
                feelings=feelings,
                helps_with=helps_with,
                negatives=negatives,
                flavors=flavors,
                terpenes=[CompactTerpene(name=t.name) for t in (strain.terpenes or []) if getattr(t, "name", None)]
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
    
    def _determine_language(self, explicit_language: Optional[str], session: ConversationSession) -> str:
        """
        Determine language with priority:
        1. Explicit language (from geolocation)
        2. Session language
        3. Default to 'es' (Spanish market default)
        """
        # Priority 1: Explicit language from request (geolocation)
        if explicit_language and explicit_language in ['es', 'en']:
            return explicit_language

        # Priority 2: Session language
        if session.detected_language and session.detected_language in ['es', 'en']:
            return session.detected_language

        # Priority 3: Default to Spanish (for Spanish-speaking markets)
        return 'es'
    
