# AI Budtender Project Guidelines 🌿

This document provides context and guidelines for Claude AI when working with the AI Budtender cannabis recommendation system.

## Project Context

AI Budtender is a production cannabis strain recommendation system that helps users find suitable strains based on their needs (sleep, energy, pain relief, etc.). The system combines LLM query analysis with fuzzy database matching and vector search to provide accurate, contextually-aware recommendations.

**Key Business Logic:**
- Users ask natural language questions about cannabis strains
- System analyzes intent, extracts criteria (category, THC level, effects)
- Database search with fallback strategies ensures relevant results
- Bilingual support (English/Spanish) with session-based conversation context

## Architecture Principles

**Current Working Architecture (DO NOT CHANGE):**
- **Async-first design**: Main pipeline uses `aprocess_contextual_query()` with dedicated ThreadPoolExecutor for DB operations
- **Single source of truth**: `SmartRAGService` is the main orchestrator - all queries flow through it
- **Session management**: Redis-backed conversations with 4-hour TTL and 7-day backup
- **Fuzzy matching**: PostgreSQL pg_trgm for typo tolerance (threshold 0.3)
- **Vector search**: Pre-computed embeddings with cosine similarity ranking

## Code Guidelines for Claude

### ✅ **What to DO:**

**Follow Existing Patterns:**
- Always use async/await for new async functions
- Use `SmartRAGService(repository=None)` pattern for async-only entry points
- Maintain session context via `session_manager.py` Redis operations
- Use structured logging with contextual information
- Follow existing error handling patterns with graceful fallbacks

**Safe Modifications:**
- Add new features by extending existing services, not replacing them
- Use composition over inheritance for new components
- Add comprehensive tests for any new functionality
- Maintain backward compatibility with existing API responses

**Database Operations:**
- Use `StrainRepository` methods for all DB access
- Prefer async database operations via ThreadPoolExecutor
- Always check for data quality (exclude strains with invalid THC/CBD data)
- Use fuzzy matching for user input processing

### ❌ **What NOT to DO:**

**Architecture Changes:**
- Never replace `SmartRAGService` - it's the proven working system
- Don't create parallel processing pipelines - use the existing async flow
- Don't modify core session management logic without explicit approval
- Avoid synchronous database calls in the async pipeline

**Deleted/Legacy Code:**
- Never reference these removed files: `smart_query_analyzer.py`, `universal_action_executor.py`, `context_provider.py`, `optimized_rag_service.py`
- Don't implement "Smart Query Executor v3.0" or "Context-Aware v2.0" - these were replaced
- Avoid feature flags like `USE_CONTEXTUAL_RAG` - they were removed

**Data Safety:**
- Don't modify strain data without backup procedures
- Never bypass rate limiting or session locking mechanisms
- Avoid hardcoded strain names or medical advice in responses

## Key Files and Their Purpose

**Core Services (app/core/):**
- `smart_rag_service.py` - **Main orchestrator** - handles all query processing
- `streamlined_analyzer.py` - LLM query analysis and intent detection
- `vector_search_service.py` - Semantic search with OpenAI embeddings
- `session_manager.py` - Redis session management with distributed locking
- `taxonomy_cache.py` - Database taxonomy caching for LLM context
- `fuzzy_matcher.py` - PostgreSQL trigram similarity matching

**Critical:** If you're unsure about a file's purpose or whether it's active, check imports in `smart_rag_service.py` - it's the authoritative source.

## Development Workflow

1. **Before Making Changes:**
   - Run existing tests to ensure nothing is broken
   - Check if similar functionality already exists
   - Verify you're working with current, non-deprecated code

2. **Testing Requirements:**
   - All 16 existing tests must pass after changes
   - New features require corresponding test coverage
   - Load simulation tests for performance-critical changes

3. **Deployment Considerations:**
   - System is containerized with Docker Compose
   - Redis and PostgreSQL dependencies must be maintained
   - OpenAI API integration is production-critical

## Current Production Status

- **Async pipeline** fully implemented and tested with granular concurrency
- **Session management** working with distributed locking and race condition protection
- **Fuzzy matching** handles typos with 90% accuracy
- **Vector search** optimized with pre-computed embeddings
- **Rate limiting** and monitoring in place for production use

**Integration Ready:** System provides stable API for cannamente UI integration.

## Questions to Ask

When in doubt about implementation decisions:
- "Does this maintain the async-first architecture?"
- "Will this break existing session management?"
- "Is there already a pattern for this in SmartRAGService?"
- "Does this require changes to the proven working pipeline?"

Follow these guidelines to maintain system stability while adding value through careful, well-tested enhancements.