# Canagent - AI Cannabis Strain Recommendation System

🌿 **Smart cannabis strain recommendations using Streamlined RAG v4.0 with LLM-driven analysis, PostgreSQL fuzzy matching, and vector semantic search.**

> **Architecture**: Streamlined RAG v4.0 - simplified query processing (LLM Analysis → SQL Pre-filtering → Attribute Filtering → Vector Search)

> **Multi-language support**: English & Spanish with dual embeddings (embedding_en, embedding_es)

> **Latest**: Streamlined RAG v4.0 with Specific Strain Queries and Enhanced CBD Filtering (January 2025)

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.9+
- OpenAI API Key (or use mock mode for development)

### Daily Workflow

```bash
# Morning (after reboot):
cd ../canna && docker-compose -f docker-compose.local.yaml up -d
cd ../canagent && make start

# During the day:
make sync-strains      # sync structured data from cannamente
make logs              # view logs
make status            # check service status

# Evening:
make stop
cd ../canna && docker-compose -f docker-compose.local.yaml down
```

### Initial Setup

1. **Create environment file:**
```bash
cp env.example .env
# Edit OPENAI_API_KEY and cannamente integration settings
```

2. **Start the system:**
```bash
make start
```

3. **Initialize database and sync data:**
```bash
# Full database initialization (for first time or after reset)
docker compose exec api python scripts/init_database.py

# Or use regular sync for updates
make sync-strains     # Syncs feelings, effects, medical uses + embeddings
```

## 🎯 Key Features (Latest Release)

### ✅ STAGE 1: Multilingual Support (EN/ES)
- **Dual Embeddings**: Separate 1536-dimensional vectors for English (`embedding_en`) and Spanish (`embedding_es`)
- **Multilingual Fields**: All metadata (feelings, helps_with, flavors, negatives) available in both languages
- **Language Detection**: Automatic query language detection with appropriate embedding selection
- **Database Migration**: Single unified migration (`001_init_multilingual_database.sql`) creates complete multilingual structure
- **Synced Data**: 173 strains with dual embeddings from cannamente database

### ✅ STAGE 2: Terpenes Support
- **Terpenes Database**: 8 terpenes synced with 172 strain-terpene relationships (87 strains have terpenes)
- **Embedding Integration**: Terpenes included in vector embeddings for improved semantic search
- **API Response**: Terpenes available in `CompactStrain` schema via `terpenes` field
- **Scientific Names**: Terpene names with descriptors (e.g., "Caryophyllene (picante)", "Limonene (citrus)")

### ✅ STAGE 3: Streamlined RAG v4.0 (Current Architecture)
- **LLM Query Analysis**: Intent detection, category extraction, attribute filtering (flavors, effects, medical uses)
- **SQL Pre-filtering**: Category, THC/CBD thresholds applied first with PostgreSQL pg_trgm trigram similarity (fuzzy matching)
- **Attribute Filtering**: Universal filtering on flavors, effects, helps_with, negatives, terpenes with trigram similarity
- **Vector Search**: Top candidates re-ranked by cosine similarity with query embedding
- **Language-Aware**: Uses `embedding_es` for Spanish queries, `embedding_en` for English
- **Specific Strain Queries**: Returns only 1 strain when user asks about specific strain by name
- **Enhanced CBD Filtering**: High CBD threshold lowered to 7% (from 10%) to include strains like Harlequin (9% CBD)

## 🎯 API Usage Examples

### Enhanced Strain Recommendations with Terpenes

```bash
# Spanish query with multilingual support
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Recomiéndame cepas índica con alto THC para dormir profundamente"}'
```

**Optimized Response Format (with Terpenes):**
```json
{
  "response": "Aquí tienes algunas cepas índicas con alto THC que pueden ayudarte a dormir...",
  "recommended_strains": [
    {
      "id": 42,
      "name": "Northern Lights",
      "cbd": "0.10",
      "thc": "18.50",
      "cbg": "1.00",
      "category": "Indica",
      "slug": "northern-lights",
      "url": "http://localhost:8000/strain/northern-lights/",
      "feelings": [
        {"name": "Sleepy"},
        {"name": "Relaxed"},
        {"name": "Hungry"}
      ],
      "helps_with": [
        {"name": "Insomnia"},
        {"name": "Stress"},
        {"name": "Pain"}
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
      "terpenes": [
        {"name": "Myrcene (herbal)"},
        {"name": "Pinene (woody)"},
        {"name": "Caryophyllene (picante)"}
      ]
    }
  ],
  "detected_intent": "search_strains",
  "filters_applied": {
    "preferred_categories": ["Indica"],
    "medical_priority": ["Insomnia"]
  },
  "session_id": "b3ee3812-17b1-4b18-ba0a-4dc846ad01d3",
  "query_type": "search_strains",
  "language": "es",
  "confidence": 0.95
}
```

### Browse Strains
```bash
# List all available strains
curl http://localhost:8001/api/v1/strains/

# Get specific strain by ID
curl http://localhost:8001/api/v1/strains/2
```

### Multi-language Examples
```bash
# English Query
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for creativity and focus"}'

# Spanish Query (cannamente style)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué me recomiendas para creatividad y concentración?"}'
```

## ⚙️ Configuration

### Environment Variables

**Cannamente Integration:**
```env
# Cannamente URL Configuration
CANNAMENTE_BASE_URL=http://localhost:8000
STRAIN_URL_PATTERN=/strain/{slug}/

# Cannamente Database (External source database)
CANNAMENTE_DATABASE_URL=postgresql://myuser:mypassword@host-gateway:5432/mydatabase
CANNAMENTE_POSTGRES_HOST=host-gateway
CANNAMENTE_POSTGRES_PORT=5432
CANNAMENTE_POSTGRES_DB=mydatabase
CANNAMENTE_POSTGRES_USER=myuser
CANNAMENTE_POSTGRES_PASSWORD=mypassword
```

**OpenAI Settings:**
```env
# Production Setup
OPENAI_API_KEY=your_actual_api_key_here
MOCK_MODE=false                    # Use real OpenAI API

# Development Setup
MOCK_MODE=true                     # Use mock responses (saves API costs)
```

**Performance & Security:**
```env
# Redis Caching
REDIS_HOST=redis
REDIS_PORT=6379

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Streamlined RAG v4.0 Settings
ANALYSIS_CACHE_TTL=1800
MAX_CONTEXT_TOKENS=4000
MIN_CONFIDENCE_THRESHOLD=0.3
ENABLE_AI_REASONING_DEBUG=false
```

## 🛠 Commands

### Core Operations
```bash
make start           # Start all services
make stop            # Stop services
make restart         # Restart everything
make logs            # Real-time logs
make status          # Check service status
```

### Data Management
```bash
make sync-strains       # Sync strains from cannamente (PRIMARY METHOD)
make test               # Run tests

# Production deployment scripts:
docker compose exec api python scripts/init_database.py      # Full initialization
docker compose exec api python scripts/sync_daily.py        # Incremental sync
```

## 🏗 Architecture

```
┌─────────────────┐    ┌──────────────────────────────────┐    ┌─────────────────┐
│   Cannamente    │    │        Canagent v7.0             │    │   Client App    │
│   (Source DB)   │───▶│   (Streamlined RAG v4.0)         │───▶│   (Frontend)    │
│                 │    │                                  │    │                 │
│ - Strain data   │    │ 🌐 Dual Embeddings (EN/ES)      │    │ - Session Mgmt  │
│ - Feelings      │    │ 🌿 Terpenes Support             │    │ - Multi-step UI │
│ - Medical uses  │    │ 🔍 Streamlined Search Flow      │    │ - Quick Actions │
│ - Effects       │    │ 🧠 LLM Query Analysis           │    │ - Terpene Info  │
│ - Terpenes      │    │ 🎯 pg_trgm Trigram Similarity   │    │ - Specific Info │
│ - PostgreSQL    │    │ ⚡ Vector Semantic Search       │    │                 │
└─────────────────┘    └──────────────────────────────────┘    └─────────────────┘
```

## 🌐 API Endpoints

### Health & Status
```bash
# Health check
curl http://localhost:8001/api/v1/ping/

# Metrics (Prometheus format)
curl http://localhost:8001/metrics
```

### Strain API
```bash
# List all strains with URLs
curl http://localhost:8001/api/v1/strains/

# Get specific strain
curl http://localhost:8001/api/v1/strains/1

# Filter by query parameters
curl "http://localhost:8001/api/v1/strains/?limit=10&skip=0"
```

### Enhanced Chat API

```bash
# Sleep/Relaxation Query (Spanish)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Necesito algo para dormir bien"}'

# Energy/Focus Query (English)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need energy and focus for work"}'

# Pain Relief Query with High THC
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What helps with chronic pain? I prefer high THC strains"}'
```

### Complete API Response Format

**All fields returned in `recommended_strains` array:**

```json
{
  "response": "Based on your need for sleep, I recommend these Indica strains...",
  "recommended_strains": [
    {
      "id": 123,
      "name": "Northern Lights",

      // Cannabinoid content
      "cbd": "0.10",        // CBD percentage (can be null)
      "thc": "18.50",       // THC percentage
      "cbg": "1.00",        // CBG percentage (can be null)

      // Classification
      "category": "Indica", // Indica/Sativa/Hybrid

      // Navigation for cannamente UI
      "slug": "northern-lights",
      "url": "http://localhost:8000/strain/northern-lights/",

      // Effects and characteristics (with energy_type)
      "feelings": [
        {"name": "Sleepy", "energy_type": "relaxing"},
        {"name": "Relaxed", "energy_type": "relaxing"},
        {"name": "Hungry", "energy_type": "neutral"}
      ],
      "helps_with": [
        {"name": "Insomnia"},
        {"name": "Stress"},
        {"name": "Pain"}
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
      "terpenes": [
        {"name": "Myrcene"},
        {"name": "Pinene"},
        {"name": "Caryophyllene"}
      ]
    }
  ],

  // AI analysis metadata
  "detected_intent": "search_strains",
  "filters_applied": {
    "filters": {...},      // Detailed filter criteria
    "scoring": {...},      // Priority scoring rules
    "sort": {...},         // Sorting configuration
    "exclude_invalid": [], // Data quality filters
    "limit": 5,
    "reasoning": "...",    // AI reasoning explanation
    "query": "...",        // Original query
    "language": "es"
  },

  // Session management
  "session_id": "uuid-here",
  "query_type": "search_strains",
  "language": "es",
  "confidence": 0.95,

  // UI enhancements
  "quick_actions": [
    "Ver el más potente",
    "Ver el más suave",
    "Comparar efectos"
  ],

  // Status flags
  "is_restored": false,
  "is_fallback": false,
  "warnings": []
}
```

### Field Reference for Cannamente Developers

**Strain Object Fields (`recommended_strains` array):**

| Field | Type | Description | Example | Required |
|-------|------|-------------|---------|----------|
| `id` | integer | Unique strain identifier | `123` | ✅ |
| `name` | string | Clean strain name only | `"Northern Lights"` | ✅ |
| `cbd` | string/null | CBD percentage as string | `"0.10"` or `null` | ❌ |
| `thc` | string/null | THC percentage as string | `"18.50"` | ❌ |
| `cbg` | string/null | CBG percentage as string | `"1.00"` or `null` | ❌ |
| `category` | string/null | Strain type | `"Indica"`, `"Sativa"`, `"Hybrid"` | ❌ |
| `slug` | string/null | URL-friendly identifier | `"northern-lights"` | ❌ |
| `url` | string/null | Direct link to strain page | `"http://localhost:8000/strain/northern-lights/"` | ❌ |
| `feelings` | array | Effects with energy type | `[{"name": "Sleepy", "energy_type": "relaxing"}]` | ✅ |
| `helps_with` | array | Medical uses/conditions | `[{"name": "Insomnia"}]` | ✅ |
| `negatives` | array | Side effects | `[{"name": "Dry mouth"}]` | ✅ |
| `flavors` | array | Taste/aroma profiles | `[{"name": "earthy"}]` | ✅ |
| `terpenes` | array | Terpene compounds | `[{"name": "Myrcene"}]` | ✅ |

**Top-Level Response Fields:**

| Field | Type | Description | Example | Required |
|-------|------|-------------|---------|----------|
| `response` | string | AI-generated text response | `"Based on your need..."` | ✅ |
| `recommended_strains` | array | Array of strain objects | `[{...}, {...}]` | ✅ |
| `detected_intent` | string | Primary action detected | `"search_strains"` | ✅ |
| `filters_applied` | object | Detailed filter/scoring info | `{"filters": {...}}` | ✅ |
| `session_id` | string | Session UUID | `"uuid-here"` | ✅ |
| `query_type` | string | Query classification | `"search_strains"` | ✅ |
| `language` | string | Detected language | `"es"` or `"en"` | ✅ |
| `confidence` | float | Analysis confidence | `0.95` | ✅ |
| `quick_actions` | array | Dynamic UI suggestions | `["Ver el más potente"]` | ❌ |
| `is_restored` | boolean | Session restored flag | `false` | ❌ |
| `is_fallback` | boolean | Fallback analysis used | `false` | ❌ |
| `warnings` | array | Analysis warnings | `[]` | ❌ |

**Nested Object Details:**

- `feelings[].energy_type`: `"energizing"`, `"relaxing"`, or `"neutral"`
- `filters_applied.filters`: Detailed filter criteria by field
- `filters_applied.scoring`: Medical priority and weighting rules
- `filters_applied.reasoning`: AI explanation of search strategy

## 📊 Monitoring & Performance

### Built-in Monitoring
- **Prometheus Metrics**: Request counts, response times, error rates
- **Redis Caching**: Query caching, connection pooling
- **Structured Logging**: JSON format, searchable logs
- **Health Checks**: Automatic service health monitoring

### Key Metrics
```bash
# Check system metrics
curl http://localhost:8001/metrics | grep -E "(http_requests|cache_hits|openai_calls)"

# Database health
make check-db
```

### Performance Optimization
- **Hybrid Search**: SQL pre-filtering + vector reranking for optimal speed
- **Dual Embeddings**: Language-specific embeddings for better relevance
- **Smart Caching**: Embedding caching with TTL for faster responses
- **Async Operations**: Non-blocking API calls
- **Rate Limiting**: Protects against API abuse

## 🔧 Ports & Services

| Service | Port | Purpose | Environment Variable |
|---------|------|---------|---------------------|
| API Server | 8001 | Main application | `API_PORT` |
| Metrics | 9091 | Prometheus metrics | `METRICS_EXTERNAL_PORT` |
| Redis | 6380 | Caching layer | `REDIS_EXTERNAL_PORT` |
| Local DB | 5433 | Application database | `DB_EXTERNAL_PORT` |
| Cannamente DB | 5432 | Source data (external) | `CANNAMENTE_POSTGRES_PORT` |

## 🧪 Testing

### Automated Tests
```bash
# Run all tests
make test

# Tests include multilingual support and terpenes
python -m pytest tests/ -v
```

### Manual Testing
```bash
# Health check
curl http://localhost:8001/api/v1/ping/

# Multilingual strain search (Spanish)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -d '{"message": "Recomiéndame cepas para dormir con terpenos relajantes"}'

# Multilingual strain search (English)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -d '{"message": "Recommend strains for sleep with relaxing terpenes"}'
```

## 🛡 Security & Production

### Security Features
- ✅ **Rate Limiting**: 100 requests/minute per IP
- ✅ **Input Validation**: Pydantic schemas
- ✅ **Environment Variables**: Secure configuration
- ✅ **CORS Protection**: Configurable origins
- ✅ **Structured Logging**: Audit trail

### Production Checklist
- [ ] Set `MOCK_MODE=false` and add real `OPENAI_API_KEY`
- [ ] Configure `CANNAMENTE_BASE_URL` for your domain
- [ ] Customize `STRAIN_URL_PATTERN` for your URL structure
- [ ] Set up log aggregation (ELK, Grafana)
- [ ] Configure backup for PostgreSQL data
- [ ] Set up monitoring alerts
- [ ] Review and customize CORS settings

## 🔄 Data Synchronization

### Production-Ready Scripts
```bash
# Full database initialization (for deployment)
docker compose exec api python scripts/init_database.py

# Daily incremental synchronization
docker compose exec api python scripts/sync_daily.py

# Regular sync via Makefile (uses sync_strain_relations.py)
make sync-strains
```

### Data Flow
1. **Source**: Cannamente PostgreSQL (Spanish strain data + terpenes)
2. **Sync**: Automatic data sync with change detection
3. **Processing**: Dual vector embeddings generation (EN + ES) with terpenes
4. **Storage**: Local PostgreSQL with pgvector and multilingual indexes
5. **API**: Multi-language strain recommendations with terpenes and URLs

## 🗂 Project Structure

```
canagent/
├── app/                    # Application source code
│   ├── api/               # REST API endpoints
│   │   ├── chat.py       # Chat API with multilingual support
│   │   ├── health.py     # Health checks and monitoring
│   │   └── strains.py    # Strain management API
│   ├── core/              # Core business logic (Streamlined RAG v4.0)
│   │   ├── smart_rag_service.py      # Main RAG Service (Streamlined RAG v4.0)
│   │   ├── streamlined_analyzer.py   # LLM query analysis with intent detection
│   │   ├── category_filter.py        # SQL filters (category, THC, CBD)
│   │   ├── vector_search_service.py  # Vector semantic search
│   │   ├── session_manager.py        # Redis-backed session management
│   │   ├── llm_interface.py          # OpenAI/Mock interface
│   │   ├── cache.py                  # Redis caching layer
│   │   ├── metrics.py                # Prometheus metrics
│   │   ├── taxonomy_cache.py         # DB-Aware: Redis + in-memory taxonomy cache
│   │   ├── fuzzy_matcher.py          # DB-Aware: pg_trgm trigram similarity
│   │   ├── context_builder.py        # DB-Aware: Dynamic LLM context from DB
│   │   └── taxonomy_init.py          # DB-Aware: System initialization
│   ├── db/                # Database layer
│   │   ├── database.py   # Connection + multilingual models
│   │   ├── repository.py # Repository with attribute filtering + terpenes
│   │   └── taxonomy_repository.py    # DB-Aware: Taxonomy data access
│   ├── models/            # Data models
│   │   ├── database.py   # SQLAlchemy models (Strain + Terpenes)
│   │   ├── schemas.py    # Pydantic schemas (CompactStrain + CompactTerpene)
│   │   └── session.py    # Session models for conversation context
│   └── utils/             # Utilities
├── tests/                 # Test suite
├── scripts/               # Automation scripts
│   ├── sync_strain_relations.py  # Full sync with terpenes (working script)
│   ├── init_database.py          # Production database initialization
│   ├── sync_daily.py             # Daily incremental synchronization
│   └── common.py                 # Shared sync functions
├── migrations/            # Database migrations
│   └── 001_init_multilingual_database.sql  # Unified multilingual migration
├── docker-compose.yml     # Docker configuration
├── env.example           # Environment variables template
├── Dockerfile            # Container definition
├── Makefile              # Command automation
└── requirements.txt      # Python dependencies
```

## 📝 Changelog

### 🚀 v7.0 - Streamlined RAG v4.0 (January 2025) - LATEST
**🎯 MAJOR RELEASE: Simplified architecture with LLM-driven analysis and enhanced filtering**

- ✅ **Streamlined Query Processing Flow**
  - LLM query analysis with intent detection (search vs non-search queries)
  - SQL pre-filtering with PostgreSQL pg_trgm trigram similarity (fuzzy matching)
  - Universal attribute filtering (flavors, effects, helps_with, negatives, terpenes)
  - Vector semantic search for final ranking

- ✅ **Specific Strain Queries**
  - Detection of queries about specific strains by name ("do you have info about X?")
  - Returns only 1 strain instead of 5 similar strains
  - Fallback to vector search if exact name not found

- ✅ **Enhanced CBD Filtering**
  - High CBD threshold lowered from 10% to 7%
  - Now includes strains like Harlequin (9% CBD) in medical queries

- ✅ **Code Cleanup & Simplification**
  - Removed 6 deprecated modules (~2,500 lines): smart_query_analyzer.py, universal_action_executor.py, context_provider.py, rag_service.py, rag_with_profiling.py, performance_profiler.py
  - Single unified architecture (no feature flags)
  - Simplified smart_rag_service.py by 300+ lines
  - Comprehensive test suite (21 tests, 90.5% pass rate)

**Technical Improvements:**
- ✅ Non-search query detection (greetings, help requests, thanks)
- ✅ PostgreSQL pg_trgm extension for trigram similarity matching (typo tolerance)
- ✅ Session-based context preservation
- ✅ Follow-up query detection
- ✅ Bilingual support (EN/ES) with language auto-detection

### 🔧 v7.1 - DB-Aware Architecture Phase 1 (January 2025)
**🎯 Intelligent taxonomy caching and fuzzy matching**

- ✅ **TaxonomyCache** - Redis + in-memory dual caching (1-hour TTL, graceful degradation)
- ✅ **FuzzyMatcher** - pg_trgm trigram similarity with threshold 0.3 ("mint" → "menthol")
- ✅ **ContextBuilder** - Dynamic LLM context from DB (replaces hardcoded taxonomy)
- ✅ **TaxonomyRepository** - Data access layer for characteristics (SOLID principles)

**Benefits:**
- No more hardcoded taxonomy in prompts (DRY principle)
- Automatic updates when DB changes (cache invalidation)
- Better fuzzy matching: trigram similarity vs simple ILIKE
- LLM receives ALL available characteristics from DB

### v6.0 - Multilingual Hybrid RAG with Terpenes (January 2025)
**🎯 Complete multilingual support with hybrid search and terpenes**

- ✅ **STAGE 1: Multilingual Embeddings**
  - Dual embeddings (`embedding_en`, `embedding_es`) for all 173 strains
  - Unified migration `001_init_multilingual_database.sql` creates complete multilingual structure
  - Automatic language detection with appropriate embedding selection
  - All metadata available in English and Spanish

- ✅ **STAGE 2: Terpenes Support**
  - 8 terpenes synced with 172 strain-terpene relationships
  - Terpenes included in vector embeddings for improved semantic search
  - `CompactTerpene` schema added to API responses
  - Repository methods updated with `joinedload(StrainModel.terpenes)`

- ✅ **STAGE 3: Hybrid Search (SQL + Vector Reranking)**
  - `hybrid_search_strains()` method combining SQL pre-filtering with vector similarity
  - SmartQueryAnalyzer adds `query` and `language` to ActionPlan parameters
  - UniversalActionExecutor performs vector reranking on top candidates
  - Combined scoring: Medical priority (50%) + Vector similarity (50%)
  - Language-aware: Uses `embedding_es` for Spanish, `embedding_en` for English

**Technical Improvements:**
- ✅ Single unified migration for all multilingual features
- ✅ Optimized database queries with proper `joinedload()` for terpenes
- ✅ Vector reranking with configurable pool size (top 20 candidates)
- ✅ Graceful fallback to SQL-only if embedding generation fails
- ✅ Production-ready with comprehensive testing

### v5.0 - Smart Query Executor v3.0 (December 2024)
- ✅ AI-driven query analysis with medical-first prioritization
- ✅ Universal action executor without hardcoded intent types
- ✅ Penalty-based medical scoring for balanced recommendations
- ✅ Automatic invalid data exclusion
- ✅ Simplified codebase with legacy code removal

### v4.1 - Enhanced Filtering & Stability
- 🔧 SQL DISTINCT/ORDER BY conflict resolution
- 🌿 Better sleep recommendations with Indica + Hybrid support
- ⚡ Energy queries include energizing Hybrid strains
- 📊 More variety with Hybrid strains in all intent filters

### Major Problems Solved ✨

**v7.0 Improvements (Latest)**:
- ✅ **Specific Strain Queries**: "do you have info about X?" now returns only 1 strain (not 5 similar)
- ✅ **Enhanced CBD Filtering**: Harlequin (9% CBD) now included in high CBD queries (threshold: 10% → 7%)
- ✅ **Simplified Architecture**: Removed 2,500+ lines of deprecated code, single unified system
- ✅ **Intent Detection**: Greetings/help queries no longer trigger unnecessary searches

**v6.0 Foundation**:
- Dual embeddings for English & Spanish queries
- Complete terpenes data with 172 relationships
- Hybrid search (SQL + Vector) for optimal results

---

## 🎯 Ready to Use!

**Quick start:** `make start` and begin making API calls with Streamlined RAG v4.0 - simplified, faster, and more accurate.

**New Features:**
- Ask about specific strains: "do you have info about Northern Lights?" → Returns only that strain
- Better medical queries: High CBD queries now include Harlequin (9% CBD)
- Smarter intent detection: Greetings don't trigger unnecessary searches

**Integration:** Configure your cannamente domain and start receiving clickable strain links with complete terpene information.

**Documentation:** All endpoints documented with examples above. Check STREAMLINED_RAG_ARCHITECTURE.md for technical details.

**Support:** Check logs with `make logs` or status with `make status`.

**Community:** This is a modern, production-ready AI strain recommendation system with Streamlined RAG v4.0, multilingual support, and intelligent query processing. 🌿
