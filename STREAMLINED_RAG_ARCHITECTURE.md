# AI Budtender Architecture - Technical Documentation

## Overview

AI Budtender is a cannabis strain recommendation system combining LLM-based query analysis, SQL pre-filtering with PostgreSQL fuzzy matching, and vector semantic search. The system provides context-aware strain recommendations with async processing and Redis-based session management.

**Key Features:**
- ✅ Async pipeline with granular concurrency
- ✅ SQL pre-filtering with fuzzy matching (handles typos)
- ✅ Attribute filtering (flavors, effects, medical uses, terpenes)
- ✅ Bilingual support (English/Spanish)
- ✅ Session-based context preservation
- ✅ Fallback strategies for zero-result scenarios

---

## Prerequisites
- PostgreSQL with `pgvector` extension
- Redis for session management
- OpenAI API key or MOCK_MODE for embeddings
- Data sync: `python scripts/sync_strain_relations.py`

## Architecture Flow

```
┌─────────────────────────────────────────────┐
│              User Query                      │
│    "suggest indica tropical high thc"       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│         SmartRAGService (Async)             │
│  - Session management & context             │
│  - Async/sync pipeline coordination         │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│    StreamlinedQueryAnalyzer                 │
│  - Intent detection (search vs greeting)    │
│  - Extract: category, THC/CBD, attributes   │
│  - Language detection (en/es)               │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│         SQL Pre-filtering                   │
│  - Category: WHERE category = 'Indica'      │
│  - THC/CBD ranges based on low/med/high     │
│  - Only active strains                      │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│       Attribute Filtering                   │
│  - FuzzyMatcher (pg_trgm, threshold 0.3)    │
│  - Flavors, effects, medical uses           │
│  - Handles typos: "mint" → "menthol"        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│       VectorSearchService                   │
│  - Semantic similarity ranking              │
│  - Language-aware embeddings                │
│  - Cosine similarity scoring                │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│           ChatResponse                      │
│  - Natural language response               │
│  - Ranked strain recommendations            │
│  - Applied filters metadata                │
└─────────────────────────────────────────────┘
```

---

## Core Components

### 1. SmartRAGService
**File:** `app/core/smart_rag_service.py`

**Purpose:** Main orchestration service with async processing pipeline

**Key Methods:**
- `aprocess_contextual_query()` - Async entry point for all queries
- `_async_streamlined_process_query()` - Main async processing pipeline
- `_apply_attribute_filters()` - Fuzzy matching for strain attributes
- Session management and context preservation

**Architecture:**
- Async-only processing with dedicated ThreadPoolExecutor for DB operations
- Session-based context management via Redis
- Graceful fallback strategies for edge cases

---

### 2. StreamlinedQueryAnalyzer
**File:** `app/core/streamlined_analyzer.py`

**Purpose:** LLM-based query analysis and intent detection

**QueryAnalysis Model:**
```python
class QueryAnalysis(BaseModel):
    # Basic filters
    detected_category: Optional[str]  # Indica/Sativa/Hybrid
    thc_level: Optional[str]  # low/medium/high
    cbd_level: Optional[str]  # low/medium/high

    # Intent detection
    is_search_query: bool  # True for strain search, False for greetings

    # Attribute filters (fuzzy matched in SQL)
    required_flavors: Optional[List[str]]
    required_effects: Optional[List[str]]
    required_helps_with: Optional[List[str]]
    exclude_negatives: Optional[List[str]]
    required_terpenes: Optional[List[str]]

    # Response
    natural_response: str
    suggested_follow_ups: List[str]
    detected_language: str  # en/es
    confidence: float
```

**Key Features:**
- Dynamic DB context injection
- Bilingual support (English/Spanish)
- Fallback to rule-based analysis if LLM fails

---

### 3. VectorSearchService
**File:** `app/core/vector_search_service.py`

**Purpose:** Semantic search using pre-computed embeddings

**Key Methods:**
- `search(query, candidates, language, limit)` - Main search method
- `agenerate_embedding()` - Async embedding generation
- `_search_with_embedding()` - Cosine similarity ranking

**Features:**
- Batch processing for efficiency
- Language-aware (embedding_en/embedding_es columns)
- Pre-computed strain embeddings

---

### 4. Database-Aware Components

#### TaxonomyCache
**File:** `app/core/taxonomy_cache.py`
- Redis + in-memory dual caching
- 1-hour TTL for taxonomy data
- Language-specific caching (EN/ES)

#### FuzzyMatcher
**File:** `app/core/fuzzy_matcher.py`
- PostgreSQL pg_trgm trigram similarity
- Threshold 0.3 for typo tolerance
- Example: "mint" → "menthol" (score: 0.42)

#### ContextBuilder
**File:** `app/core/context_builder.py`
- Injects DB taxonomy into LLM prompts
- Replaces hardcoded flavor/effect lists
- Ensures LLM uses actual DB values

---

### 5. Session Management
**File:** `app/core/vector_search_service.py`

**Purpose:** Batch vector embedding and semantic search

**Main Methods:**

#### `search(query, candidates, language, limit)`
Perform semantic search on pre-filtered candidates.

**Algorithm:**
1. Generate query embedding (using OpenAI API)
2. For each candidate: extract existing embedding (embedding_en or embedding_es)
3. Calculate cosine similarity scores
4. Sort by similarity descending
5. Return top N strains

**Optimization:**
- Batch processing (no N+1 queries)
- Uses pre-computed embeddings from database
- Language-aware (uses correct embedding column)

---

### 5. DB-Aware Architecture (Phase 1)

**Purpose:** Intelligent taxonomy caching and fuzzy matching with dynamic LLM context

#### TaxonomyCache
**File:** `app/core/taxonomy_cache.py`

**Features:**
- Dual caching: Redis (primary) + in-memory (fallback)
- 1-hour TTL (3600s) for taxonomy data
- Graceful degradation on Redis failure
- Language-specific caching (EN/ES separate keys)
- Warm cache on startup

**Usage:**
```python
cache = TaxonomyCache(repository, redis_client)
taxonomy = cache.get_taxonomy("es")  # Returns all flavors, effects, medical uses, etc.
```

#### FuzzyMatcher
**File:** `app/core/fuzzy_matcher.py`

**Strategy Pattern:**
- `TrigramMatcher` - pg_trgm similarity (threshold 0.3)
- `ExactMatcher` - Direct match fallback
- `CompositeMatcher` - Combines both strategies

**Example:**
```python
matcher = create_composite_matcher(db_session)
matches = matcher.match("mint", ["menthol", "mint", "lemon"], threshold=0.3)
# Returns: [MatchResult("mint", 1.0), MatchResult("menthol", 0.42)]
```

#### ContextBuilder
**File:** `app/core/context_builder.py`

**Purpose:** Build dynamic LLM context from DB taxonomy (replaces hardcoded lists)

**Features:**
- Loads ALL characteristics from DB (not truncated)
- Formats for LLM prompt section
- Language-aware context building
- Statistics for monitoring

**Integration:**
```python
context_builder = create_context_builder(taxonomy_cache)
llm_context = context_builder.build_llm_context(query, language="es")
prompt_section = context_builder.build_prompt_section(llm_context)
# LLM receives: "Available flavors: tropical, citrus, ... (all DB values)"
```

#### TaxonomyRepository
**File:** `app/db/taxonomy_repository.py`

**Purpose:** Data access layer for taxonomy (SOLID principles)

**Methods:**
- `get_all_flavors()` - Returns bilingual flavor list
- `get_all_feelings()` - Returns bilingual effects
- `get_all_helps_with()` - Returns bilingual medical uses
- `get_all_negatives()` - Returns bilingual side effects
- `get_all_terpenes()` - Returns terpene list
- `get_thc_range()`, `get_cbd_range()`, `get_categories()`

---

### 6. Session Management
**File:** `app/core/session_manager.py`

**Purpose:** Redis-backed session management

**Features:**
- 4-hour TTL for active sessions, 7-day backup
- Conversation & strain recommendation history
- Distributed locking for race condition protection
- Graceful session restoration

---

## Processing Examples

### Search Query Processing
```
"suggest indica tropical high thc"
↓
1. LLM Analysis: category=Indica, thc_level=high, flavors=[tropical]
2. SQL Filtering: WHERE category='Indica' AND thc >= 20
3. Attribute Filtering: JOIN flavors WHERE name LIKE 'tropical'
4. Vector Search: Semantic ranking of remaining candidates
5. Response: Natural language + ranked strains
```

### Non-Search Queries
Greetings and general questions return text-only responses without triggering strain search.

---

## Fallback Strategies

1. **Attribute Filtering:** If filters remove all candidates, fall back to SQL pre-filtering results
2. **LLM Failure:** Rule-based keyword matching if OpenAI API unavailable
3. **Zero Results:** Gradual filter relaxation (strict → category only → semantic search)

---

## Database Schema

**Key Tables:**
- `strains_strain` - Main strain data (THC/CBD/CBG, category, embeddings)
- `strains_flavor` - Bilingual flavor names (name_en, name_es)
- `strains_feeling` - Effects (relaxed, sleepy, energetic, etc.)
- `strains_helpswith` - Medical uses (pain, anxiety, insomnia, etc.)
- `strains_negative` - Side effects (dry mouth, paranoia, etc.)
- `strains_terpene` - Terpene profiles

**Relations:** Many-to-many joins between strains and attributes

---

## Performance

**Typical Response Times:**
- LLM analysis: 2-4 seconds
- SQL pre-filtering: 10-20ms
- Attribute filtering: 20-30ms
- Vector search: 50-100ms

**Features:**
- Async pipeline with granular concurrency
- PostgreSQL fuzzy matching with 90% typo coverage
- Redis caching with 1-hour TTL for taxonomy data

---

## Configuration

**Required Environment Variables:**
```bash
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://user:password@host:5432/ai_budtender
REDIS_HOST=redis
REDIS_PORT=6379
```

**Optional:**
```bash
SESSION_TTL=14400  # 4 hours
BACKUP_TTL=604800  # 7 days
```

---

## Deployment

**Development:**
```bash
docker compose up -d
docker compose exec api python scripts/sync_strain_relations.py
```

**Ports:**
- API: 8001
- Redis: 6380
- Database: 5433

---

**Last Updated:** February 2025
