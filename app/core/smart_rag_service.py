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

        # --- Fast pre-filter: skip LLM for obvious non-search queries ---
        quick_response = self._try_quick_response(query, detected_language)
        if quick_response is not None:
            logger.info("⚡ Quick response (pre-filter) - skipping LLM")
            analysis = QueryAnalysis(
                detected_category=None,
                is_search_query=False,
                natural_response=quick_response["response"],
                suggested_follow_ups=quick_response["follow_ups"],
                detected_language=detected_language,
                confidence=0.95,
            )
            db_svc._update_session_streamlined(session, query, analysis, [])
            await self.session_manager.asave_session_with_backup(session)
            return await run_db(
                db_svc._build_streamlined_response,
                analysis, [], session,
                {"is_search_query": False, "reason": "quick_pre_filter"}
            )

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
                {"is_search_query": True, "is_follow_up": True, "deterministic_executor": True}
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
                {"is_search_query": True, "specific_strain_query": True, "strain_name": analysis.specific_strain_name}
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

        # ASYNC: Vector search — async embedding (with cache) + DB distance calculation
        if candidates:
            try:
                # Check embedding cache first
                from app.core.cache import cache_service
                query_embedding = await cache_service.get_embedding(query)
                if query_embedding is None:
                    query_embedding = await db_svc.vector_search.llm.agenerate_embedding(query)
                    if not query_embedding or len(query_embedding) == 0:
                        raise ValueError("Empty embedding received from LLM")
                    await cache_service.set_embedding(query, query_embedding)
                else:
                    logger.info("Embedding cache hit")

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

        # ASYNC LLM: Response generation with real strain names (~0.5-1s, no thread)
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

    async def aprocess_contextual_query_streaming(
        self,
        query: str,
        session_id: Optional[str] = None,
        language: Optional[str] = None,
        history: Optional[List[str]] = None,
        source_platform: Optional[str] = None
    ):
        """
        Streaming version of aprocess_contextual_query.

        Yields JSON-serializable dicts:
        1. First yield: {"type": "metadata", ...} with strains, filters, session_id etc.
        2. Subsequent yields: {"type": "response_chunk", "text": "..."} with streaming text
        3. Final yield: {"type": "done"}

        The non-streaming pipeline runs analysis → DB → vector search as normal,
        then streams only the mini-prompt response generation.
        """
        import json as _json

        logger.info(f"Streaming processing query: {query[:50]}...")

        async with self.session_manager.async_session_lock(session_id):
            session = await self.session_manager.aget_or_restore_session(session_id)

            loop = asyncio.get_event_loop()
            db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-stream")
            db_ref = [None]

            def _init_db():
                from app.db.database import SessionLocal
                db = SessionLocal()
                db_ref[0] = db
                repo = StrainRepository(db)
                return SmartRAGService(repo)

            db_svc = await loop.run_in_executor(db_executor, _init_db)

            def run_db(fn, *args):
                return loop.run_in_executor(db_executor, fn, *args)

            try:
                detected_language = db_svc._determine_language(language, session)

                # Quick pre-filter
                quick_response = self._try_quick_response(query, detected_language)
                if quick_response is not None:
                    analysis = QueryAnalysis(
                        detected_category=None,
                        is_search_query=False,
                        natural_response=quick_response["response"],
                        suggested_follow_ups=quick_response["follow_ups"],
                        detected_language=detected_language,
                        confidence=0.95,
                    )
                    db_svc._update_session_streamlined(session, query, analysis, [])
                    await self.session_manager.asave_session_with_backup(session)
                    response = await run_db(
                        db_svc._build_streamlined_response,
                        analysis, [], session,
                        {"is_search_query": False, "reason": "quick_pre_filter"}
                    )
                    yield {"type": "metadata", "data": _json.loads(response.model_dump_json())}
                    yield {"type": "done"}
                    return

                session_context = db_svc._build_session_context(session)
                session_strains = await run_db(db_svc._get_session_strains, session)

                analysis_context = session_context.copy()
                if session_strains:
                    analysis_context['recommended_strains'] = [
                        f"{s.name} ({s.category}, THC: {s.thc}%)"
                        for s in session_strains[:5]
                    ]
                else:
                    analysis_context['recommended_strains'] = []

                # LLM Analysis
                try:
                    analysis = await db_svc.streamlined_analyzer.aanalyze_query(
                        user_query=query,
                        session_context=analysis_context,
                        found_strains=None,
                        explicit_language=detected_language
                    )
                except Exception as e:
                    logger.error(f"Streaming analysis failed: {e}", exc_info=True)
                    analysis = QueryAnalysis(
                        detected_category=None, is_search_query=True, is_follow_up=False,
                        natural_response="I can help you find the right strain.",
                        suggested_follow_ups=[], detected_language=detected_language, confidence=0.5
                    )

                # Non-search branch
                if not analysis.is_search_query:
                    db_svc._update_session_streamlined(session, query, analysis, [])
                    await self.session_manager.asave_session_with_backup(session)
                    response = await run_db(
                        db_svc._build_streamlined_response,
                        analysis, [], session,
                        {"is_search_query": False, "reason": "greeting_or_general_question"}
                    )
                    yield {"type": "metadata", "data": _json.loads(response.model_dump_json())}
                    yield {"type": "done"}
                    return

                # Follow-up branch
                if analysis.is_follow_up and session_strains:
                    from app.core.follow_up_executor import detect_follow_up_intent_keywords
                    intent = analysis.follow_up_intent
                    if not intent:
                        intent = detect_follow_up_intent_keywords(query)
                    result_strains, deterministic_response = db_svc.follow_up_executor.execute(
                        intent=intent, session_strains=session_strains, language=analysis.detected_language
                    )
                    analysis.natural_response = deterministic_response
                    db_svc._update_session_streamlined(session, query, analysis, result_strains)
                    await self.session_manager.asave_session_with_backup(session)
                    response = await run_db(
                        db_svc._build_streamlined_response,
                        analysis, result_strains, session,
                        {"is_search_query": True, "is_follow_up": True, "deterministic_executor": True}
                    )
                    yield {"type": "metadata", "data": _json.loads(response.model_dump_json())}
                    yield {"type": "done"}
                    return

                # Specific strain branch
                if analysis.specific_strain_name:
                    def _find_specific():
                        specific = db_svc.repository.db.query(StrainModel).filter(
                            StrainModel.name.ilike(analysis.specific_strain_name),
                            StrainModel.active == True
                        ).first()
                        if specific:
                            return [specific], False
                        all_s = db_svc.repository.db.query(StrainModel).filter(StrainModel.active == True).all()
                        return all_s, True

                    found_strains, needs_vs = await run_db(_find_specific)
                    if needs_vs and found_strains:
                        query_emb = await db_svc.vector_search.llm.agenerate_embedding(analysis.specific_strain_name)
                        result_strains = await run_db(
                            db_svc.vector_search._search_with_embedding,
                            query_emb, found_strains, analysis.detected_language, 1
                        )
                    else:
                        result_strains = found_strains
                    db_svc._update_session_streamlined(session, query, analysis, result_strains)
                    await self.session_manager.asave_session_with_backup(session)
                    response = await run_db(
                        db_svc._build_streamlined_response,
                        analysis, result_strains, session,
                        {"is_search_query": True, "specific_strain_query": True}
                    )
                    yield {"type": "metadata", "data": _json.loads(response.model_dump_json())}
                    yield {"type": "done"}
                    return

                # Main search path
                def _db_filter_phase():
                    filter_params = {'is_search_query': True}
                    if analysis.detected_category:
                        filter_params['category'] = analysis.detected_category
                    if analysis.thc_level == "low":
                        filter_params['max_thc'] = 10
                    elif analysis.thc_level == "medium":
                        filter_params['min_thc'] = 10; filter_params['max_thc'] = 20
                    elif analysis.thc_level == "high":
                        filter_params['min_thc'] = 20
                    if analysis.cbd_level == "low":
                        filter_params['max_cbd'] = 3
                    elif analysis.cbd_level == "medium":
                        filter_params['min_cbd'] = 3; filter_params['max_cbd'] = 10
                    elif analysis.cbd_level == "high":
                        filter_params['min_cbd'] = 7
                    filter_chain = db_svc.filter_factory.create_from_params(filter_params)
                    base_query = db_svc.repository.db.query(StrainModel)
                    filtered_query = filter_chain.apply(base_query)
                    candidates = filtered_query.all()
                    if candidates and (analysis.required_flavors or analysis.required_effects or
                                      analysis.required_helps_with or analysis.exclude_negatives or
                                      analysis.required_terpenes):
                        original_count = len(candidates)
                        candidates = db_svc._apply_attribute_filters(candidates, analysis, filter_params)
                        if not candidates:
                            candidates = filtered_query.all()
                            filter_params['attribute_fallback'] = True
                    return candidates, filter_params

                candidates, filter_params = await run_db(_db_filter_phase)

                fallback_used = False
                if not candidates:
                    fallback_used = True
                    def _fallback():
                        if analysis.thc_level or analysis.cbd_level:
                            fb_params = {}
                            if analysis.detected_category:
                                fb_params['category'] = analysis.detected_category
                            fb_chain = db_svc.filter_factory.create_from_params(fb_params)
                            fb = fb_chain.apply(db_svc.repository.db.query(StrainModel)).all()
                            if fb:
                                return fb
                        return db_svc.repository.db.query(StrainModel).filter(StrainModel.active == True).all()
                    candidates = await run_db(_fallback)

                # Vector search
                if candidates:
                    try:
                        from app.core.cache import cache_service
                        query_embedding = await cache_service.get_embedding(query)
                        if query_embedding is None:
                            query_embedding = await db_svc.vector_search.llm.agenerate_embedding(query)
                            await cache_service.set_embedding(query, query_embedding)
                        result_strains = await run_db(
                            db_svc.vector_search._search_with_embedding,
                            query_embedding, candidates, analysis.detected_language, 5
                        )
                    except Exception as e:
                        logger.error(f"Streaming vector search failed: {e}", exc_info=True)
                        result_strains = candidates[:5]
                else:
                    result_strains = []

                # Preserve LLM natural_response for empty-results fallback,
                # then replace with placeholder so _update_session_streamlined
                # doesn't save "..." — session history is updated AFTER streaming.
                original_natural_response = analysis.natural_response
                analysis.natural_response = "..."

                if fallback_used and result_strains:
                    if analysis.detected_language == 'es':
                        fallback_notice = "ℹ️ No encontré coincidencias exactas. Aquí están las opciones más cercanas:\n\n"
                    else:
                        fallback_notice = "ℹ️ No exact matches found. Here are the closest options:\n\n"
                else:
                    fallback_notice = ""

                # Save session now (provides session_id for metadata), history entry
                # will be updated with real response text after streaming completes.
                db_svc._update_session_streamlined(session, query, analysis, result_strains)
                await self.session_manager.asave_session_with_backup(session)

                metadata_response = await run_db(
                    db_svc._build_streamlined_response,
                    analysis, result_strains, session, filter_params
                )

                # Yield metadata (strains, filters, session_id).
                # response field is intentionally empty — real text comes via response_chunks.
                metadata_dict = _json.loads(metadata_response.model_dump_json())
                metadata_dict["response"] = ""
                yield {"type": "metadata", "data": metadata_dict}

                # Stream the natural language response and accumulate for session history.
                full_response = ""
                if result_strains:
                    strain_info = [
                        {'name': s.name, 'category': s.category, 'thc': str(s.thc) if s.thc else 'N/A'}
                        for s in result_strains[:5]
                    ]
                    if fallback_notice:
                        yield {"type": "response_chunk", "text": fallback_notice}
                        full_response += fallback_notice
                    async for chunk in db_svc.streamlined_analyzer.astream_response_only(
                        query=query, strains=strain_info, language=detected_language
                    ):
                        yield {"type": "response_chunk", "text": chunk}
                        full_response += chunk
                else:
                    # No strains found even after fallback — use LLM's natural_response directly.
                    if original_natural_response and original_natural_response != "...":
                        yield {"type": "response_chunk", "text": original_natural_response}
                        full_response = original_natural_response

                yield {"type": "done"}

                # Update session history with the real streamed response.
                if session.conversation_history and full_response:
                    session.conversation_history[-1]['response'] = full_response
                    await self.session_manager.asave_session_with_backup(session)

            finally:
                if db_ref[0]:
                    await loop.run_in_executor(db_executor, db_ref[0].close)
                db_executor.shutdown(wait=False)

    # ---- Helper methods used by async pipeline ----

    # Greeting/non-search patterns for fast pre-filtering (avoids ~4s LLM call)
    _GREETING_PATTERNS_EN = {
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "bye", "goodbye", "see you", "cheers",
    }
    _GREETING_PATTERNS_ES = {
        "hola", "buenos dias", "buenos días", "buenas tardes", "buenas noches",
        "gracias", "muchas gracias", "adios", "adiós", "hasta luego", "chao",
    }
    _HELP_PATTERNS_EN = {"what can you do", "how can you help", "help me", "what do you do"}
    _HELP_PATTERNS_ES = {"que puedes hacer", "qué puedes hacer", "como me ayudas", "cómo me ayudas", "ayudame", "ayúdame"}
    _CHITCHAT_PATTERNS = {"how are you", "como estas", "cómo estás", "what's up", "que tal", "qué tal"}

    def _try_quick_response(self, query: str, language: str) -> Optional[Dict[str, Any]]:
        """
        Fast keyword-based pre-filter for obvious non-search queries.
        Returns a response dict if matched, None otherwise (falls through to LLM).
        Only matches clear, unambiguous non-search patterns.
        """
        q = query.lower().strip().rstrip("!?.,:;")

        # Check greetings
        if q in self._GREETING_PATTERNS_EN or q in self._GREETING_PATTERNS_ES:
            if language == "es":
                return {
                    "response": "¡Hola! Soy tu budtender virtual. Puedo ayudarte a encontrar la cepa perfecta según tus necesidades: para dormir, energía, dolor, o cualquier efecto que busques. ¿Qué estás buscando?",
                    "follow_ups": ["Cepas para dormir", "Sativas energéticas", "Alto CBD para dolor"],
                }
            return {
                "response": "Hi there! I'm your virtual budtender. I can help you find the perfect strain based on your needs: sleep, energy, pain relief, or any specific effects. What are you looking for?",
                "follow_ups": ["Strains for sleep", "Energetic sativas", "High CBD for pain"],
            }

        # Check help requests
        if q in self._HELP_PATTERNS_EN or q in self._HELP_PATTERNS_ES:
            if language == "es":
                return {
                    "response": "Puedo ayudarte a encontrar cepas de cannabis según tus preferencias. Dime qué efectos buscas (relajación, energía, creatividad), para qué condición (dolor, insomnio, ansiedad), o qué tipo prefieres (indica, sativa, híbrido).",
                    "follow_ups": ["Indica para relajar", "Sativa para energía", "Alto CBD medicinal"],
                }
            return {
                "response": "I can help you find cannabis strains based on your preferences. Tell me what effects you're looking for (relaxation, energy, creativity), what condition (pain, insomnia, anxiety), or what type you prefer (indica, sativa, hybrid).",
                "follow_ups": ["Indica for relaxation", "Sativa for energy", "High CBD medical"],
            }

        # Check chitchat
        if q in self._CHITCHAT_PATTERNS:
            if language == "es":
                return {
                    "response": "¡Todo bien! Estoy aquí para ayudarte a encontrar la cepa ideal. ¿Qué estás buscando hoy?",
                    "follow_ups": ["Cepas para dormir", "Algo energético", "Recomendaciones populares"],
                }
            return {
                "response": "I'm doing great! I'm here to help you find your ideal strain. What are you looking for today?",
                "follow_ups": ["Strains for sleep", "Something energetic", "Popular recommendations"],
            }

        return None

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
    
