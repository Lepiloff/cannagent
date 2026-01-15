# Streamlined RAG Architecture v4.1 - Technical Documentation

## Overview

**Streamlined RAG v4.1** is a cannabis strain recommendation system that combines LLM-based query analysis, SQL pre-filtering with fuzzy matching, and vector semantic search to provide accurate, context-aware strain recommendations.

**Key Features:**
- ✅ Query Intent Detection (search vs non-search queries)
- ✅ SQL Pre-filtering with PostgreSQL fuzzy matching (handles typos)
- ✅ Universal attribute filtering (flavors, effects, medical uses, terpenes)
- ✅ Bilingual support (English/Spanish)
- ✅ **Deterministic follow-up execution** (eliminates hallucinations)
- ✅ **Mini-prompt re-analysis** (10x smaller, 3-4x faster)
- ✅ Fallback strategies for zero-result scenarios

### v4.1 Improvements (January 2025)

| Metric | v4.0 | v4.1 | Improvement |
|--------|------|------|-------------|
| **Hallucination Rate** | 28.6% | 0.0% | -100% |
| **Average Latency** | 12,237ms | 6,554ms | -46% |
| **Prompt Size** | ~22k chars | ~15k chars | -32% |

---

## Database Prereqs (prod/local)
- PostgreSQL with `pgvector` extension (`CREATE EXTENSION IF NOT EXISTS vector;`).
- Schema is managed via Alembic: run `docker compose exec api alembic upgrade head` before starting (deploy workflow runs this automatically).
- Data + embeddings can be synced from cannamente via `python scripts/sync_strain_relations.py` (needs `CANNAMENTE_*` env and `OPENAI_API_KEY` or `MOCK_MODE=true` for mock embeddings).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                                │
│                  "suggest indica tropical high thc"              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: LLM Query Analysis (StreamlinedQueryAnalyzer)          │
│  - Intent detection: is_search_query?                           │
│  - Category extraction: Indica/Sativa/Hybrid                    │
│  - THC/CBD levels: low/medium/high                              │
│  - Attributes: flavors, effects, helps_with, negatives          │
│  - Language detection: en/es                                    │
│  - Follow-up intent extraction (FollowUpIntent model)           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                   ┌─────────┴─────────┐
                   │                   │
                   ▼                   ▼
        ┌──────────────────┐  ┌──────────────────────────────────┐
        │ is_search_query? │  │  is_follow_up? (v4.1 IMPROVED)   │
        │      FALSE       │  │         TRUE                      │
        └────────┬─────────┘  └────────┬─────────────────────────┘
                 │                     │
                 ▼                     ▼
        ┌──────────────────┐  ┌──────────────────────────────────┐
        │ Return text-only │  │ DETERMINISTIC EXECUTOR           │
        │ NO strains       │  │ FollowUpExecutor.execute()       │
        └──────────────────┘  │ - Python code, NOT LLM           │
                              │ - Zero hallucinations guaranteed │
                              │ - Actions: compare/filter/sort/  │
                              │   select/describe                 │
                              └────────┬─────────────────────────┘
                   │                   │
                   │ is_search_query = TRUE (NEW search)
                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: SQL Pre-filtering (Category/THC/CBD)                   │
│  FilterFactory.create_from_params()                             │
│  - CategoryFilter: WHERE category = 'Indica'                    │
│  - THCRangeFilter: WHERE thc >= 20                              │
│  - CBDRangeFilter: WHERE cbd >= 10 (if requested)               │
│  Result: 12 candidates                                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Attribute Filtering (Fuzzy Matching)                   │
│  SmartRAGService._apply_attribute_filters()                     │
│                                                                  │
│  PostgreSQL pg_trgm trigram similarity:                         │
│  - Uses FuzzyMatcher with threshold 0.3                         │
│  - Flavors: similarity(user_input, name_en) > 0.3              │
│  - Effects: similarity matching on feelings table               │
│  - Medical uses: similarity matching on helps_with table        │
│  - Exclude negatives: NOT IN (...)                              │
│                                                                  │
│  Handles typos: "mint" → "menthol" (score: 0.42) ✓              │
│  Result: 2 candidates                                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Vector Semantic Search                                 │
│  VectorSearchService.search()                                   │
│  - Batch embedding generation for remaining candidates          │
│  - Cosine similarity ranking                                    │
│  - Language-aware (uses embedding_en or embedding_es)           │
│  Result: 2 strains ranked by semantic similarity                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Mini-prompt Response Generation (v4.1 OPTIMIZED)       │
│  StreamlinedQueryAnalyzer.generate_response_only()              │
│  - ~1k chars prompt (vs ~22k for full analysis)                 │
│  - 10x smaller, 3-4x faster                                     │
│  - Generates natural response with strain names                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ChatResponse                                │
│  - natural_response: "Te recomiendo Watermelon Zkittlez..."     │
│  - recommended_strains: [Forbidden Fruit, Watermelon Zkittlez]  │
│  - filters_applied: {category: Indica, flavors: [tropical]}     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. StreamlinedQueryAnalyzer
**File:** `app/core/streamlined_analyzer.py`

**Purpose:** LLM-based query analysis and intent detection

**Key Classes:**
- `QueryAnalysis` - Pydantic model with query analysis results
- `StreamlinedQueryAnalyzer` - Main analyzer class

**Main Methods:**
- `analyze_query(user_query, session_context, found_strains, fallback_used)` - Primary analysis method
- `generate_response_only(query, strains, language)` - **NEW in v4.1** Mini-prompt for fast response generation
- `_build_context()` - Build context for LLM
- `_analyze_with_llm()` - Call LLM with minimal prompt
- `_parse_result()` - Parse and validate LLM response
- `_fallback_analysis()` - Rule-based fallback if LLM fails

**FollowUpIntent Model (NEW in v4.1):**
```python
class FollowUpIntent(BaseModel):
    """Structured intent for deterministic follow-up execution"""
    action: Literal["compare", "filter", "sort", "select", "describe"]
    field: Optional[str]  # thc, cbd, category
    order: Optional[Literal["asc", "desc"]]  # for compare/sort
    filter_value: Optional[str]  # e.g., "Indica"
    strain_indices: Optional[List[int]]  # for select action
```

**QueryAnalysis Fields:**
```python
class QueryAnalysis(BaseModel):
    # Basic filters
    detected_category: Optional[str]  # Indica/Sativa/Hybrid
    thc_level: Optional[str]  # low/medium/high
    cbd_level: Optional[str]  # low/medium/high

    # Intent detection
    is_search_query: bool  # True for strain search, False for greetings
    is_follow_up: bool  # True for follow-up queries
    follow_up_intent: Optional[FollowUpIntent]  # NEW: structured intent for deterministic execution

    # Attribute filters (extracted as written, fuzzy matched in SQL)
    required_flavors: Optional[List[str]]  # e.g., ['tropical', 'citrus']
    required_effects: Optional[List[str]]  # e.g., ['relaxed', 'sleepy']
    required_helps_with: Optional[List[str]]  # e.g., ['pain', 'anxiety']
    exclude_negatives: Optional[List[str]]  # e.g., ['paranoia']
    required_terpenes: Optional[List[str]]  # e.g., ['myrcene']

    # Response
    natural_response: str
    suggested_follow_ups: List[str]
    detected_language: str  # en/es
    confidence: float
```

**LLM Prompt Strategy (v4.1 optimized):**
- Reduced prompt (~15k chars vs ~22k in v4.0)
- **6 key examples** (reduced from 16)
- **Dynamic DB context**: Uses ContextBuilder to inject ALL available taxonomy from DB
- Follow-up intent extraction for deterministic execution
- Bilingual keyword support
- Fuzzy matching instructions: extract "as written" (typos OK)

---

### 2. SmartRAGService
**File:** `app/core/smart_rag_service.py`

**Purpose:** Main orchestration service - coordinates analysis, filtering, and search

**Main Methods:**

#### `process_contextual_query(query, session_id, history, source_platform)`
Entry point for all queries. Routes to `_streamlined_process_query()`.

#### `_streamlined_process_query(query, session)`
Main processing pipeline:

1. **LLM Analysis** - Call `StreamlinedQueryAnalyzer.analyze_query()`
2. **Intent Routing:**
   - If `is_search_query = False` → return text-only response (no strain search)
   - If `is_follow_up = True` → **DETERMINISTIC EXECUTOR** (v4.1) - no LLM, no hallucinations
3. **SQL Pre-filtering** - Build filter chain (category, THC, CBD)
4. **Attribute Filtering** - Call `_apply_attribute_filters()`
5. **Vector Search** - Call `VectorSearchService.search()`
6. **Mini-prompt Response** (v4.1) - Call `generate_response_only()` (~10x smaller prompt)
7. **Session Update** - Save conversation and strains
8. **Build Response** - Return `ChatResponse`

#### `_apply_attribute_filters(candidates, analysis, filter_params)`
**Purpose:** Filter strains by exact attributes using PostgreSQL pg_trgm trigram similarity

**Algorithm:**
```python
# For each attribute type (flavors, effects, helps_with, negatives, terpenes):
1. Use FuzzyMatcher to resolve user inputs to DB values
   matches = fuzzy_matcher.match(user_input, db_candidates, threshold=0.3)

2. FuzzyMatcher uses pg_trgm trigram similarity:
   SELECT value, similarity(:user_input, value) as score
   WHERE similarity(:user_input, value) > 0.3
   ORDER BY score DESC

3. Join with strain table and filter candidate IDs
   query.join(Strain.flavors).filter(id IN candidates).filter(matched_values)

4. Return filtered list (graceful fallback if 0 results)
```

**Example:**
```python
# User input: "mint"
# Trigram similarity scores: "menthol" (0.42), "mint" (1.0)
# Matches: ["menthol", "mint"] (both above 0.3 threshold) ✓
```

**Supported Attributes:**
- **Flavors:** tropical, citrus, earthy, pine, sweet, berry, diesel, etc.
- **Effects (Feelings):** relaxed, sleepy, happy, energetic, focused, creative, etc.
- **Medical Uses (Helps_with):** pain, anxiety, stress, insomnia, depression, etc.
- **Negatives:** dry mouth, dry eyes, paranoia, anxiety, dizzy, headache
- **Terpenes:** myrcene, limonene, pinene, caryophyllene, linalool, humulene

**Fallback Logic:**
```python
if not candidates:  # Attribute filters too strict
    logger.warning("Falling back to category/THC/CBD results")
    candidates = original_sql_filtered_candidates
    filter_params['attribute_fallback'] = True
```

#### `_build_session_context(session)`
Build minimal context for LLM analyzer.

#### `_get_session_strains(session)`
Retrieve strains from previous recommendation for follow-up queries.

#### `_update_session_streamlined(session, query, analysis, strains)`
Update session with conversation and strain history.

#### `_build_streamlined_response(analysis, strains, session, filters)`
Build final `ChatResponse` with strains and metadata.

---

### 3. FollowUpExecutor (NEW in v4.1)
**File:** `app/core/follow_up_executor.py`

**Purpose:** Deterministic execution of follow-up queries - eliminates LLM hallucinations

**Key Principle:** LLM determines WHAT to do (intent), Python code determines HOW to do it (execution).

**Why This Matters:**
- **Before v4.1:** LLM generated responses for follow-up queries, often hallucinating strain names not in session
- **After v4.1:** Python code executes operations on session strains - mathematically correct, zero hallucinations

**Supported Actions:**

| Action | Description | Example Query |
|--------|-------------|---------------|
| `compare` | Find highest/lowest by field | "which has highest THC?" |
| `sort` | Sort strains by field | "sort by CBD" |
| `filter` | Filter by category | "show only indica" |
| `select` | Select specific strain | "tell me about the first one" |
| `describe` | Describe all strains | "what are these?" |

**Usage:**
```python
from app.core.follow_up_executor import FollowUpExecutor, FollowUpIntent

executor = FollowUpExecutor()

# Intent extracted by LLM (or keyword detection fallback)
intent = FollowUpIntent(action="compare", field="thc", order="desc")

# Execute deterministically - guaranteed to use ONLY session strains
result_strains, response = executor.execute(
    intent=intent,
    session_strains=session_strains,  # From previous query
    language="en"
)
# response: "From the previous list, Kush Mints has the highest THC at 28.0%."
```

**Keyword Detection Fallback:**
```python
from app.core.follow_up_executor import detect_follow_up_intent_keywords

# If LLM fails to extract intent, fallback to keyword detection
intent = detect_follow_up_intent_keywords("which one is strongest")
# Returns: FollowUpIntent(action="compare", field="thc", order="desc")
```

---

### 4. FilterFactory & Filter Classes (renumbered)
**File:** `app/core/category_filter.py`

**Purpose:** SQL filter builders for category, THC, CBD ranges

**Classes:**
- `StrainFilter` - Base abstract class
- `CategoryFilter` - Filter by Indica/Sativa/Hybrid
- `ActiveOnlyFilter` - Only active strains
- `THCRangeFilter` - Min/max THC filtering
- `CBDRangeFilter` - Min/max CBD filtering
- `FilterChain` - Chain multiple filters together
- `FilterFactory` - Factory for creating filter chains from params

**Usage:**
```python
filter_params = {
    'category': 'Indica',
    'min_thc': 20,
    'max_cbd': 3
}

chain = FilterFactory.create_from_params(filter_params)
# Returns: FilterChain with:
#   - ActiveOnlyFilter (always added)
#   - CategoryFilter(Indica)
#   - THCRangeFilter(min=20)

query = chain.apply(base_query)  # Apply all filters sequentially
candidates = query.all()
```

---

### 4. VectorSearchService
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

**Purpose:** Redis-backed session storage for conversation context

**Key Features:**
- 4-hour TTL for active sessions
- 7-day backup for preferences
- Conversation history (max 50 entries)
- Strain recommendation history (max 20 groups)

**Session Model:**
```python
class ConversationSession:
    session_id: str
    detected_language: str  # en/es
    conversation_history: List[Dict]  # Recent queries and responses
    recommended_strains_history: List[List[int]]  # Strain IDs by query
    user_preferences: Dict  # Inferred preferences
    created_at: datetime
    last_updated: datetime

    def get_last_strains() -> List[int]:
        """Get strain IDs from most recent recommendation"""
```

---

## Query Processing Flow

### Example 1: New Search Query

**Input:**
```json
{
  "message": "suggest me indica with tropical flavor and high thc"
}
```

**Step-by-Step:**

1. **LLM Analysis:**
```python
QueryAnalysis(
    is_search_query=True,  # It's a search request
    detected_category="Indica",
    thc_level="high",  # > 20%
    required_flavors=["tropical"],
    detected_language="en"
)
```

2. **SQL Pre-filtering:**
```sql
-- ActiveOnlyFilter
WHERE active = true

-- CategoryFilter
AND category = 'Indica'

-- THCRangeFilter (high = min 20%)
AND thc >= 20

-- Result: 12 candidates
```

3. **Attribute Filtering:**
```sql
-- Flavor filter with fuzzy matching
SELECT DISTINCT strains.*
FROM strains_strain
JOIN strains_strain_flavors ON ...
JOIN strains_flavor ON ...
WHERE strains_strain.id IN (12_candidate_ids)
  AND (strains_flavor.name_en ILIKE '%tropi%'
       OR strains_flavor.name_es ILIKE '%tropi%')

-- Result: 2 candidates (Forbidden Fruit, Watermelon Zkittlez)
```

4. **Vector Search:**
```python
# Rank 2 candidates by semantic similarity
query_embedding = embed("suggest me indica with tropical flavor and high thc")
similarities = [
    cosine_sim(query_embedding, forbidden_fruit.embedding_en),  # 0.92
    cosine_sim(query_embedding, watermelon_zkittlez.embedding_en)  # 0.89
]
# Sorted: [Forbidden Fruit, Watermelon Zkittlez]
```

5. **Response:**
```json
{
  "response": "I recommend Forbidden Fruit, an indica with 22% THC and tropical flavors...",
  "recommended_strains": [
    {
      "name": "Forbidden Fruit",
      "thc": "22.00",
      "category": "Indica",
      "flavors": ["mango", "tropical", "grapefruit"]
    },
    {
      "name": "Watermelon Zkittlez",
      "thc": "24.00",
      "category": "Indica",
      "flavors": ["berry", "tropical", "sweet"]
    }
  ],
  "filters_applied": {
    "is_search_query": true,
    "category": "Indica",
    "min_thc": 20,
    "flavors": ["tropical"]
  }
}
```

---

### Example 2: Non-Search Query (Greeting)

**Input:**
```json
{
  "message": "hey, how can you help me"
}
```

**Step-by-Step:**

1. **LLM Analysis:**
```python
QueryAnalysis(
    is_search_query=False,  # It's a greeting, NOT a search
    detected_category=None,
    natural_response="Hi! I'm your cannabis budtender. I can help you find...",
    suggested_follow_ups=["Show me relaxing strains", "I need help with sleep"],
    detected_language="en"
)
```

2. **Early Return (No Search):**
```python
if not analysis.is_search_query:
    return ChatResponse(
        response=analysis.natural_response,
        recommended_strains=[],  # Empty list - no strain search performed
        filters_applied={"is_search_query": False}
    )
```

**Response:**
```json
{
  "response": "Hi! I'm your cannabis budtender. I can help you find the perfect strain...",
  "recommended_strains": [],  // No unnecessary search!
  "filters_applied": {
    "is_search_query": false,
    "reason": "greeting_or_general_question"
  }
}
```

---

### Example 3: Follow-up Query (v4.1 - Deterministic Execution)

**Input:**
```json
{
  "message": "which one has highest THC",
  "session_id": "abc-123"
}
```

**Session Context:**
```python
session.recommended_strains_history = [
    [42, 158, 61]  # IDs: Super Silver Haze (21%), Chocolope (22%), Jack Herer (18%)
]
```

**Step-by-Step (v4.1 IMPROVED):**

1. **LLM Analysis - Extract Structured Intent:**
```python
QueryAnalysis(
    is_search_query=True,
    is_follow_up=True,  # References previous results
    follow_up_intent=FollowUpIntent(  # NEW: structured intent
        action="compare",
        field="thc",
        order="desc"  # highest
    ),
    natural_response="[ignored - will be replaced by deterministic executor]"
)
```

2. **Retrieve Session Strains:**
```python
session_strains = get_session_strains(session)
# Returns: [Super Silver Haze (21%), Chocolope (22%), Jack Herer (18%)]
```

3. **DETERMINISTIC EXECUTION (NEW in v4.1):**
```python
# No LLM call - pure Python execution
# Zero hallucinations possible!

from app.core.follow_up_executor import FollowUpExecutor

executor = FollowUpExecutor()
result_strains, response = executor.execute(
    intent=analysis.follow_up_intent,
    session_strains=session_strains,
    language="en"
)

# Python sorts by THC and generates response:
# response = "From the previous list, Chocolope has the highest THC at 22.0%.
#             Super Silver Haze follows with 21.0%."
```

4. **Return Response:**
```python
return ChatResponse(
    response=response,  # Deterministic, mathematically correct
    recommended_strains=result_strains,  # Sorted by THC desc
    filters_applied={"is_follow_up": True, "deterministic_executor": True}
)
```

**Response:**
```json
{
  "response": "From the previous list, Chocolope has the highest THC at 22.0%. Super Silver Haze follows with 21.0%.",
  "recommended_strains": [
    {"name": "Chocolope", "thc": "22.00", "category": "Sativa"},
    {"name": "Super Silver Haze", "thc": "21.00", "category": "Sativa"},
    {"name": "Jack Herer", "thc": "18.00", "category": "Sativa"}
  ],
  "filters_applied": {
    "is_follow_up": true,
    "deterministic_executor": true
  }
}
```

**Why This Matters:**
- **Before v4.1:** LLM might respond "GMO Cookies has the highest THC at 28%" - a strain NOT in the session (hallucination!)
- **After v4.1:** Python code sorts session strains and ALWAYS returns correct answer from available options

---

## Fallback Strategies

### 1. Attribute Filtering Fallback

**Scenario:** Attribute filters remove ALL candidates

```python
# Before: 12 candidates (Indica + high THC)
# After flavor filter: 0 candidates (too strict)

if not candidates:
    logger.warning("Attribute filters too strict - falling back")
    candidates = original_sql_filtered_candidates  # Restore to 12
    filter_params['attribute_fallback'] = True
```

**User Experience:**
- Still get relevant results (Indica + high THC)
- System notes that exact flavor match not found
- Transparent via `filters_applied` response field

---

### 2. THC/CBD Fallback

**Scenario:** Category + THC/CBD filters return 0 results

```python
# Example: "Indica with CBD > 10%" → 0 results

if not candidates:
    # Remove THC/CBD filters, keep category
    fallback_params = {'category': 'Indica'}
    candidates = apply_filters(fallback_params)
    fallback_used = True
```

**User Experience:**
- Response prefixed with notice:
  - ES: "ℹ️ No encontré coincidencias exactas. Aquí están las opciones más cercanas:"
  - EN: "ℹ️ No exact matches found. Here are the closest options:"

---

### 3. LLM Fallback

**Scenario:** LLM API unavailable or JSON parsing fails

```python
except Exception as e:
    logger.error(f"LLM analysis failed: {e}")
    return _fallback_analysis(user_query)  # Rule-based keyword matching
```

**Fallback Logic:**
```python
def _fallback_analysis(user_query):
    """Simple keyword-based analysis"""
    query_lower = user_query.lower()

    category = None
    if "indica" in query_lower: category = "Indica"
    elif "sativa" in query_lower: category = "Sativa"
    elif "hybrid" in query_lower: category = "Hybrid"

    thc_level = None
    if "high thc" in query_lower: thc_level = "high"
    elif "low thc" in query_lower: thc_level = "low"

    return QueryAnalysis(
        detected_category=category,
        thc_level=thc_level,
        confidence=0.5  # Lower confidence for fallback
    )
```

---

## Database Schema

### Core Tables

**strains_strain:**
```sql
- id: INTEGER PRIMARY KEY
- name: VARCHAR(255)
- category: VARCHAR(10)  -- Indica/Sativa/Hybrid
- thc: NUMERIC(5,2)
- cbd: NUMERIC(5,2)
- cbg: NUMERIC(5,2)
- active: BOOLEAN
- embedding_en: VECTOR(1536)  -- OpenAI embedding
- embedding_es: VECTOR(1536)  -- Spanish embedding
```

**strains_flavor:**
```sql
- id: INTEGER PRIMARY KEY
- name: VARCHAR(50)  -- Deprecated, use name_en
- name_en: VARCHAR(50)  -- English flavor name
- name_es: VARCHAR(50)  -- Spanish flavor name
```

**strains_feeling (effects):**
```sql
- id: INTEGER PRIMARY KEY
- name: VARCHAR(50)
- name_en: VARCHAR(50)
- name_es: VARCHAR(50)
```

**strains_helpswith (medical uses):**
```sql
- id: INTEGER PRIMARY KEY
- name: VARCHAR(100)
- name_en: VARCHAR(100)
- name_es: VARCHAR(100)
```

**strains_negative (side effects):**
```sql
- id: INTEGER PRIMARY KEY
- name: VARCHAR(50)
- name_en: VARCHAR(50)
- name_es: VARCHAR(50)
```

**strains_terpene:**
```sql
- id: INTEGER PRIMARY KEY
- name: VARCHAR(50)  -- Scientific name (universal)
- description: TEXT
- description_en: TEXT
- description_es: TEXT
```

### Many-to-Many Relations

- `strains_strain_flavors` - Strain → Flavors
- `strains_strain_feelings` - Strain → Effects
- `strains_strain_helps_with` - Strain → Medical Uses
- `strains_strain_negatives` - Strain → Side Effects
- `strains_strain_terpenes` - Strain → Terpenes

---

## Performance Characteristics

### v4.1 Benchmark Results (January 2025)

| Metric | v4.0 (Before) | v4.1 (After) | Improvement |
|--------|---------------|--------------|-------------|
| **Hallucination Rate** | 28.6% | 0.0% | **-100%** |
| **Average Latency** | 12,237ms | 6,554ms | **-46%** |
| **Prompt Size** | ~22k chars | ~15k chars | **-32%** |

### Token Usage

**Streamlined RAG v4.0:**
- Analysis prompt: ~22k chars (~630 lines)
- Re-analysis: Full prompt again (~22k chars)
- Total: ~44k chars per new search query

**Streamlined RAG v4.1 (OPTIMIZED):**
- Analysis prompt: ~15k chars (~480 lines) - reduced examples
- Re-analysis: Mini-prompt (~1k chars) - 10x smaller!
- Follow-up: NO LLM call - deterministic Python execution
- **Total: ~16k chars per new search query**
- **Savings: ~63% token reduction** ✓

### Latency Breakdown

**New Search Query (v4.1):**
- LLM analysis: ~3000-4000ms (reduced prompt)
- SQL pre-filtering: ~10-20ms
- Attribute filtering: ~20-30ms
- Vector search: ~50-100ms
- Mini-prompt response: ~800-1000ms (vs ~3000ms for full re-analysis)
- **Total: ~4000-5500ms** ✓

**Follow-up Query (v4.1):**
- LLM analysis (intent extraction): ~2000-3000ms
- Deterministic execution: ~1-5ms (Python, no LLM!)
- **Total: ~2000-3000ms** ✓

### Accuracy

**Hallucination Prevention:**
- v4.0: LLM could mention strains not in session (28.6% hallucination rate)
- v4.1: Deterministic executor guarantees only session strains (0% hallucination rate) ✓

**Flavor Matching:**
- Old system (vector only): ~60% precision (semantic dilution issue)
- New system (SQL fuzzy + vector): ~95% precision ✓

**Typo Handling:**
- "tropicas" → finds "tropical" ✓
- "citricos" → finds "citrus" ✓
- First 5 chars matching: ~90% typo coverage

---

## Configuration

### Environment Variables

**Required:**
```bash
# OpenAI API
OPENAI_API_KEY=sk-...

# Database
DATABASE_URL=postgresql://user:password@host:5432/ai_budtender

# Redis (Session storage)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Feature Flags
USE_STREAMLINED_RAG=true  # Enable Streamlined RAG v4.0
```

**Optional:**
```bash
# Session TTL
SESSION_TTL=14400  # 4 hours in seconds
BACKUP_TTL=604800  # 7 days in seconds

# Vector Search
VECTOR_DIMENSION=1536  # OpenAI embedding dimension
```

---

## Testing Guidelines

### Unit Tests

**Test StreamlinedQueryAnalyzer:**
```python
def test_greeting_query():
    analyzer = StreamlinedQueryAnalyzer(llm)
    result = analyzer.analyze_query("hey, how can you help me")

    assert result.is_search_query == False
    assert result.detected_category is None
    assert len(result.recommended_strains) == 0
```

**Test Attribute Filtering:**
```python
def test_flavor_fuzzy_matching():
    # Test typo handling
    result = service._apply_attribute_filters(
        candidates=all_strains,
        analysis=QueryAnalysis(required_flavors=["tropicas"])  # Typo
    )

    # Should find strains with "tropical"
    assert any("tropical" in [f.name for f in s.flavors] for s in result)
```

### Integration Tests

**Test Full Query Flow:**
```python
def test_tropical_flavor_search():
    response = client.post("/api/v1/chat/ask/", json={
        "message": "suggest me indica with tropical flavor and high thc"
    })

    data = response.json()
    assert data["filters_applied"]["flavors"] == ["tropical"]
    assert len(data["recommended_strains"]) > 0
    assert all("tropical" in [f["name"] for f in s["flavors"]]
               for s in data["recommended_strains"])
```

---

## Common Issues & Troubleshooting

### Issue 1: No Results for Valid Query

**Symptom:** Query "indica with tropical flavor" returns 0 strains

**Debug Steps:**
1. Check SQL pre-filtering: `logger.info(f"SQL filtering: {len(candidates)} candidates")`
2. Check attribute filtering: `logger.info(f"After attribute filtering: {len(candidates)}")`
3. Verify flavors exist in DB: `SELECT * FROM strains_flavor WHERE name_en ILIKE '%tropical%'`

**Common Causes:**
- Typo in flavor name (should be caught by fuzzy matching)
- No strains in DB with that combination
- Filters too strict → fallback should activate

### Issue 2: Wrong Strains Returned

**Symptom:** Query "high THC" returns low THC strains

**Debug Steps:**
1. Check LLM analysis: `logger.info(f"Analysis: thc_level={analysis.thc_level}")`
2. Check filter params: `logger.info(f"Filters: {filter_params}")`
3. Verify THC conversion: high → min_thc=20

**Common Causes:**
- LLM misinterpretation (check prompt examples)
- THC data quality (check for NULL or "N/A" values)

### Issue 3: Greeting Returns Strains

**Symptom:** "hello" query returns strain recommendations

**Debug Steps:**
1. Check LLM intent detection: `logger.info(f"is_search_query={analysis.is_search_query}")`
2. Verify prompt has greeting examples
3. Check early return logic in `_streamlined_process_query()`

**Fix:** Add more greeting examples to LLM prompt

---

## Migration from Old System

### Deprecated Components

The following components are deprecated and will be removed:

**Files to Remove:**
- `app/core/rag_service.py` - Legacy RAG without context
- `app/core/optimized_rag_service.py` - Context-Aware v2.0
- `app/core/smart_query_analyzer.py` - Smart Query Executor v3.0 analyzer
- `app/core/universal_action_executor.py` - Universal action system
- `app/core/context_provider.py` - Context building for v3.0
- `app/core/unified_processor.py` - Unified LLM processor
- `app/core/fallback_analyzer.py` - Rule-based fallback for v2.0
- `app/core/conflict_resolver.py` - Conflict resolution for v2.0
- `app/core/adaptive_search.py` - Adaptive search for v2.0

**Environment Variables to Remove:**
- `USE_STREAMLINED_RAG` - Will become the only system
- `USE_SMART_EXECUTOR` - No longer needed
- `USE_CONTEXTUAL_RAG` - Deprecated

### Migration Steps

1. **Create backup:**
   ```bash
   git checkout -b backup/pre-streamlined-cleanup
   git commit -am "Backup before Streamlined RAG v4.0 migration"
   ```

2. **Remove deprecated files:**
   ```bash
   rm app/core/rag_service.py
   rm app/core/optimized_rag_service.py
   rm app/core/smart_query_analyzer.py
   # ... (see list above)
   ```

3. **Remove feature flags from SmartRAGService:**
   - Remove `self.use_streamlined_rag` check
   - Remove `self.use_smart_executor` check
   - Keep only `_streamlined_process_query()` logic

4. **Update imports:**
   - Remove unused imports in `smart_rag_service.py`
   - Update API endpoints to remove feature flag checks

5. **Clean environment files:**
   - Remove `USE_STREAMLINED_RAG` from `.env`, `.env.example`, `docker-compose.yml`

---

## Future Enhancements

### Planned Features

1. **Caching Layer:**
   - Cache LLM analysis for common queries
   - Redis-based embedding cache
   - Estimated savings: 30-40% reduction in LLM calls

2. **Advanced Terpene Filtering:**
   - Terpene profiles (dominant vs secondary)
   - Effect-based terpene recommendations
   - Terpene synergy detection

3. **User Preference Learning:**
   - Track user interactions
   - Build preference profiles
   - Personalized ranking

4. **Multi-language Expansion:**
   - Add French, German, Italian support
   - Language-specific embeddings
   - Automatic translation fallback

---

## Glossary

**Indica/Sativa/Hybrid:** Cannabis strain categories with different effects
**THC (Tetrahydrocannabinol):** Primary psychoactive compound in cannabis
**CBD (Cannabidiol):** Non-psychoactive compound with medical benefits
**CBG (Cannabigerol):** Minor cannabinoid with therapeutic potential
**Terpenes:** Aromatic compounds that influence flavor and effects
**Fuzzy Matching:** Approximate string matching (handles typos)
**Vector Embedding:** Dense numerical representation for semantic similarity
**Cosine Similarity:** Measure of similarity between vector embeddings
**RAG (Retrieval-Augmented Generation):** Combining search + LLM generation

---

## Appendix: API Response Examples

### Successful Search Query

**Request:**
```json
POST /api/v1/chat/ask/
{
  "message": "necesito algo para dormir con alto thc",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "response": "Te recomiendo 9 lb Hammer, una indica con 20% THC perfecta para dormir profundamente. También King Louis (20% THC) es excelente para el insomnio.",
  "recommended_strains": [
    {
      "id": 123,
      "name": "9 lb Hammer",
      "category": "Indica",
      "thc": "20.00",
      "cbd": "0.10",
      "cbg": null,
      "slug": "9-lb-hammer",
      "url": "http://localhost:8000/strain/9-lb-hammer/",
      "feelings": [
        {"name": "Relaxed"},
        {"name": "Sleepy"},
        {"name": "Hungry"}
      ],
      "helps_with": [
        {"name": "Insomnia"},
        {"name": "Pain"},
        {"name": "Stress"}
      ],
      "negatives": [
        {"name": "Dry mouth"},
        {"name": "Dry eyes"}
      ],
      "flavors": [
        {"name": "earthy"},
        {"name": "pine"},
        {"name": "sweet"}
      ],
      "terpenes": []
    }
  ],
  "detected_intent": "Indica",
  "filters_applied": {
    "is_search_query": true,
    "category": "Indica",
    "min_thc": 20,
    "helps_with": ["insomnia"]
  },
  "session_id": "abc-123-def-456",
  "query_type": "streamlined_search",
  "language": "es",
  "confidence": 0.95,
  "quick_actions": [
    "¿Prefieres algo más suave?",
    "¿Necesitas ayuda con dolor también?",
    "¿Te interesan opciones con CBD?"
  ],
  "is_restored": false,
  "is_fallback": false,
  "warnings": null
}
```

### Non-Search Query (Greeting)

**Request:**
```json
POST /api/v1/chat/ask/
{
  "message": "hello, what can you do?"
}
```

**Response:**
```json
{
  "response": "Hi! I'm your AI cannabis budtender. I can help you find the perfect strain based on your needs - whether you're looking for relaxation, energy, pain relief, or specific flavors. What would you like to know?",
  "recommended_strains": [],  // Empty - no search performed
  "detected_intent": null,
  "filters_applied": {
    "is_search_query": false,
    "reason": "greeting_or_general_question"
  },
  "session_id": "new-session-xyz",
  "query_type": "streamlined_search",
  "language": "en",
  "confidence": 0.95,
  "quick_actions": [
    "Show me relaxing strains",
    "I need something for sleep",
    "What's good for pain relief?"
  ],
  "is_restored": false,
  "is_fallback": false,
  "warnings": null
}
```

---

**Document Version:** 1.1
**Last Updated:** January 2025
**System Version:** Streamlined RAG v4.1
**Status:** Production Ready ✓

### Changelog

**v4.1 (January 2025):**
- Added `FollowUpExecutor` for deterministic follow-up execution (eliminates hallucinations)
- Added `FollowUpIntent` model for structured intent extraction
- Added `generate_response_only()` mini-prompt method (10x smaller, 3-4x faster)
- Reduced prompt examples from 16 to 6 key scenarios (-32% prompt size)
- Achieved 0% hallucination rate (was 28.6%)
- Reduced average latency by 46% (12,237ms → 6,554ms)
