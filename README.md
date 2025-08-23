# Canagent - AI Cannabis Strain Recommendation System

🌿 **Smart cannabis strain recommendations using Context-Aware RAG with Session Management, Intent Detection, and Conversational Memory for multi-step cannabis consultations.**

> **Architecture**: Smart Query Executor v3.0 with Universal AI-driven criteria generation and dynamic data quality handling.

> **Multi-language support**: English (primary), Spanish (for cannamente integration)

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

## 🎯 API Usage Examples

### Context-Aware Strain Recommendations

**🆕 Multi-step Conversations with Session Management:**

```bash
# Step 1: Initial recommendation (creates session)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for relaxation and sleep", "source_platform": "cannamente"}'

# Step 2: Follow-up question (uses session context)  
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Which one is strongest?", "session_id": "YOUR_SESSION_ID", "source_platform": "cannamente"}'

# Step 3: Reset conversation
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Start new search", "session_id": "YOUR_SESSION_ID", "source_platform": "cannamente"}'
```

**Optimized Response Format for Cannamente UI:**
```json
{
  "response": "I recommend Northern Lights for relaxation and sleep...",
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
        {"name": "Dry eyes"},
        {"name": "Dizzy"}
      ],
      "flavors": [
        {"name": "earthy"},
        {"name": "pine"},
        {"name": "sweet"}
      ]
    }
  ],
  "detected_intent": "sleep",
  "filters_applied": {
    "preferred_categories": ["Indica"],
    "exclude_feelings": ["Energetic", "Talkative"]
  },
  
  // 🆕 Context-Aware Architecture v2.0 Fields
  "session_id": "b3ee3812-17b1-4b18-ba0a-4dc846ad01d3",
  "query_type": "new_search",          // new_search|follow_up|comparison|reset|clarification
  "language": "es",                     // Detected language (es/en)
  "confidence": 0.95,                   // AI confidence (0.0-1.0)
  "quick_actions": [                    // Dynamic contextual suggestions
    "Compare Northern Lights and OG Kush",
    "Show strongest option", 
    "Show mildest option",
    "Start new search"
  ],
  "is_restored": false,                 // Session was restored from backup
  "is_fallback": false,                 // Used rule-based fallback (no OpenAI)
  "warnings": []                        // Conflict resolution warnings
}
```

### Browse Strains
```bash
# List all available strains
curl http://localhost:8001/api/v1/strains/

# Get specific strain by ID
curl http://localhost:8001/api/v1/strains/2
```

### Multi-language Support
```bash
# Spanish Query (cannamente style) - Context-Aware
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué me recomiendas para creatividad y concentración?", "source_platform": "cannamente"}'

# Follow-up in Spanish (uses session context)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cuál de estos es más suave?", "session_id": "YOUR_SESSION_ID", "source_platform": "cannamente"}'
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

# 🆕 Context-Aware Architecture v2.0 Settings
USE_CONTEXTUAL_RAG=true              # Enable Context-Aware Architecture  
SESSION_TTL_HOURS=4                  # Active session duration
SESSION_BACKUP_DAYS=7                # Preference backup retention
UNIFIED_LLM_TIMEOUT=3000            # LLM timeout in milliseconds
FALLBACK_ON_TIMEOUT=true            # Use rule-based fallback
EMBEDDING_CACHE_TTL=86400           # Cache strain embeddings (24 hours)
QUERY_EMBEDDING_CACHE_TTL=3600      # Cache query embeddings (1 hour)

# 🆕 Context policy thresholds (adaptive context→expand search)
CATEGORY_MATCH_STRICT=true           # Require category match to stay in context
EFFECTS_MATCH_THRESHOLD=0.5          # If effects match ratio < threshold → expand search
FLAVORS_MATCH_THRESHOLD=0.35         # Softer threshold for flavors
MEDICAL_MATCH_THRESHOLD=0.65         # Medical coverage required to stay in context

# 🆕 Scoring weights (priority weighting)
MEDICAL_WEIGHT=12.0                  # Priority 1 (helps_with)
SECONDARY_WEIGHT=3.0                 # Priority 2 (THC/CBD/category)
TERTIARY_WEIGHT=1.0                  # Priority 3 (flavors/appearance)
```

### URL Configuration

The system generates clickable strain URLs for cannamente integration:

| Setting | Description | Example |
|---------|-------------|---------|
| `CANNAMENTE_BASE_URL` | Base URL for strain pages | `http://localhost:8000` |
| `STRAIN_URL_PATTERN` | URL pattern with slug | `/strain/{slug}/` |
| **Result** | Generated strain URL | `http://localhost:8000/strain/blue-dream/` |

**Custom Configuration Examples:**
```env
# For production domain:
CANNAMENTE_BASE_URL=https://dispensary.com
STRAIN_URL_PATTERN=/cannabis/{slug}.html
# Result: https://dispensary.com/cannabis/blue-dream.html

# For local development:
CANNAMENTE_BASE_URL=http://localhost:3000  
STRAIN_URL_PATTERN=/products/strain/{slug}/
# Result: http://localhost:3000/products/strain/blue-dream/
```

## 🔧 Tuning Guide (Thresholds & Weights)

Цель: быстро подстроить чувствительность к смене темы и приоритизацию скоринга.

### Переменные и эффект
- CATEGORY_MATCH_STRICT: true/false. При true остаёмся в контексте только если категории совпадают; иначе → expand_search.
- EFFECTS_MATCH_THRESHOLD: 0.0–1.0. Если доля совпадений эффектов ниже порога → expand_search. Ниже порог — дольше держим контекст.
- FLAVORS_MATCH_THRESHOLD: 0.0–1.0. Аналогично для вкусов (мягче по умолчанию).
- MEDICAL_MATCH_THRESHOLD: 0.0–1.0. Требуемая «покрываемость» медицинских показаний для удержания контекста.
- MEDICAL_WEIGHT / SECONDARY_WEIGHT / TERTIARY_WEIGHT: веса в приоритетном скоринге. Медицинские показатели и штрафы за противоречия масштабируются MEDICAL_WEIGHT.

Рекомендуемые значения (дефолт):
```env
CATEGORY_MATCH_STRICT=true
EFFECTS_MATCH_THRESHOLD=0.5
FLAVORS_MATCH_THRESHOLD=0.35
MEDICAL_MATCH_THRESHOLD=0.65
DOMAIN_RELEVANCE_THRESHOLD=0.2

MEDICAL_WEIGHT=12.0
SECONDARY_WEIGHT=3.0
TERTIARY_WEIGHT=1.0
```

### Рецепты
- Агрессивная смена темы (быстрее уходим в новый поиск):
```env
CATEGORY_MATCH_STRICT=true
EFFECTS_MATCH_THRESHOLD=0.6
FLAVORS_MATCH_THRESHOLD=0.5
MEDICAL_MATCH_THRESHOLD=0.7
```

- Держаться контекста дольше (меньше expand_search):
```env
CATEGORY_MATCH_STRICT=false
EFFECTS_MATCH_THRESHOLD=0.35
FLAVORS_MATCH_THRESHOLD=0.25
MEDICAL_MATCH_THRESHOLD=0.5
```

- Медицинский приоритет «жёстче» (safety-first):
```env
MEDICAL_WEIGHT=18.0
SECONDARY_WEIGHT=2.5
TERTIARY_WEIGHT=0.8
```

- Чувствительность к ароматам (например, ментол):
```env
FLAVORS_MATCH_THRESHOLD=0.5
TERTIARY_WEIGHT=1.5
```
Замечание: aroma-точность также усиливается семантическим flavor rerank (эмбеддинги + Redis кэш), это включено всегда и не требует настроек.

### Out-of-domain (вне тематики)
- Включён лёгкий OOD-детектор на евристиках. При низкой доменной релевантности агент не делает поиск и предлагает вернуться к подбору сортов.
- Порог: `DOMAIN_RELEVANCE_THRESHOLD` (0–1). Повышайте, если агент слишком часто уходит в нерелевантные ответы.

### Диагностика
- Логи: установите `LOG_LEVEL=DEBUG` для подробностей по policy hint/expand и применённым фильтрам/сортировке.
- Быстрая проверка: прогоните сценарии из разделов «Context-Aware Strain Recommendations» и «Enhanced Chat API» с разными ENV.

Границы: не ставьте пороги =1.0 (почти всегда будет expand_search) и не опускайте все пороги <0.2 (система перестанет адаптивно переключаться).

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

## 🏗 Context-Aware Architecture v2.0

```
┌─────────────────┐    ┌──────────────────────────────────┐    ┌─────────────────┐
│   Cannamente    │    │          Canagent v2.0           │    │   Client App    │
│   (Source DB)   │───▶│       (Context-Aware API)        │───▶│   (Frontend)    │
│                 │    │                                  │    │                 │
│ - Strain data   │    │ 🧠 Intent Detection              │    │ - Session Mgmt  │
│ - Feelings      │    │ 🔍 Adaptive Strain Search        │    │ - Multi-step UI │
│ - Medical uses  │    │ 🔗 Vector Search + Filters       │    │ - Quick Actions │
│ - Effects       │    │ 🤖 Unified LLM Processor         │    │ - Context UI    │
│ - PostgreSQL    │    │ ⚡ Rule-based Fallback          │    │ - Session State │
│                 │    │ 🔄 Session Management (Redis)    │    │                 │
│                 │    │ ⚖️  Conflict Resolution          │    │                 │
│                 │    │ 💾 Embedding Cache + TTL        │    │                 │
└─────────────────┘    └──────────────────────────────────┘    └─────────────────┘
```

### 🎯 Context-Aware Conversation Flow:

**1. Session Creation & Management**
- User sends first message → Creates session with 4h TTL + 7-day backup
- Follow-up messages use same session_id → Context preserved

**2. Unified Analysis (Single LLM Call)**
- Query type detection: `new_search|follow_up|comparison|reset|clarification`
- Language detection: Spanish/English with session memory
- Criteria extraction with conflict resolution

**3. Adaptive Search Strategy (5-stage fallback)**
- Stage 1: Strict filters (all criteria)
- Stage 2: Relaxed effects (remove avoid filters)  
- Stage 3: Categories only (no effects)
- Stage 4: Semantic search (no filters)
- Stage 5: Fallback (top strains)

**4. Context-Aware Response Generation**
- Session-aware responses (references previous recommendations)
- Dynamic quick actions based on current strains and context
- Warnings for resolved conflicts
- Context-first selection with adaptive expand: follow-up filters apply to current session strains; if matches are insufficient per thresholds, the system expands search to DB automatically
- Taxonomy normalization: multilingual synonyms for effects/negatives/helps_with/flavors are normalized for robust matching
- Semantic flavor rerank: flavor matching boosted by embeddings with in-memory + Redis persistent cache

**🆕 Key Features v2.0:**
- ✅ **Conversational Memory**: Multi-step dialogs with context preservation
- ✅ **Session Management**: 4-hour active sessions, 7-day preference backup  
- ✅ **Unified LLM Processing**: Single API call vs 4-5 separate calls
- ✅ **Rule-based Fallback**: Works without OpenAI for reliability
- ✅ **Adaptive Search**: Never returns 0 results with 5-stage fallback
- ✅ **Conflict Resolution**: Detects contradictions like "sleepy but energetic"
- ✅ **Dynamic UI Support**: Quick actions, quality indicators, session restore
- ✅ **Production Ready**: Proven with multi-step integration tests

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

### Enhanced Chat API with Intent Detection

```bash
# Sleep/Relaxation Query
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for sleep", "history": []}'

# Energy/Focus Query  
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need energy and focus for work", "history": []}'

# Pain Relief Query
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What helps with chronic pain?", "history": []}'
```

### Complete API Response Format (Optimized for Cannamente)

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
      
      // Effects and characteristics (arrays of objects with multiple values)
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
        {"name": "Dry eyes"},
        {"name": "Dizzy"}
      ],
      "flavors": [
        {"name": "earthy"},
        {"name": "pine"},
        {"name": "sweet"}
      ]
    }
  ],
  "detected_intent": "sleep",
  "filters_applied": {
    "preferred_categories": ["Indica"],
    "required_feelings": ["Sleepy", "Relaxed"],
    "exclude_feelings": ["Energetic", "Talkative"]
  }
}
```

### Field Reference for Cannamente Developers

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
| `feelings` | array | Effects/sensations (typically 2-4 items) | `[{"name": "Sleepy"}, {"name": "Relaxed"}, {...}]` | ✅ |
| `helps_with` | array | Medical uses/conditions (typically 2-4 items) | `[{"name": "Insomnia"}, {"name": "Stress"}, {...}]` | ✅ |
| `negatives` | array | Side effects (typically 2-4 items) | `[{"name": "Dry mouth"}, {"name": "Dry eyes"}, {...}]` | ✅ |
| `flavors` | array | Taste/aroma profiles (typically 2-4 items) | `[{"name": "earthy"}, {"name": "pine"}, {...}]` | ✅ |

**🆕 Context-Aware Architecture v2.0 Response Fields:**

| Field | Type | Description | Example | Required |
|-------|------|-------------|---------|----------|
| `session_id` | string/null | Unique session identifier for multi-step conversations | `"b3ee3812-17b1-4b18-ba0a-4dc846ad01d3"` | ❌ |
| `query_type` | string | Type of user query | `"new_search"`, `"follow_up"`, `"comparison"`, `"reset"`, `"clarification"` | ✅ |
| `language` | string | Detected language | `"es"`, `"en"` | ✅ |
| `confidence` | float | AI confidence level (0.0-1.0) | `0.95` | ✅ |
| `quick_actions` | array | Dynamic contextual suggestions | `["Compare X and Y", "Show strongest", "Start new search"]` | ❌ |
| `is_restored` | boolean | Session was restored from backup | `false` | ✅ |
| `is_fallback` | boolean | Used rule-based fallback (no OpenAI) | `false` | ✅ |
| `warnings` | array | Conflict resolution warnings | `["sleep aid"]` when user wants both sleep and energy | ❌ |

**Fields removed for optimization (not included):**
- `title` - duplicated `name`
- `text_content` - too large, use `description`
- `keywords` - SEO metadata not needed for UI
- `img`, `img_alt_text` - not synced from source
- `rating`, `active`, `top`, `main`, `is_review` - internal flags
- `created_at`, `updated_at` - timestamps (kept in DB for sync)
- `id`, `created_at` in relations - unnecessary for UI display

### Intent Detection Examples

The system automatically detects user intent and applies appropriate filtering:

| Query | Detected Intent | Preferred Categories | Required Effects | Excluded Effects |
|-------|-----------------|---------------------|------------------|------------------|
| "I need sleep" | `sleep` | Indica, Hybrid | Sleepy, Relaxed, Hungry | Energetic, Talkative |
| "Need energy for work" | `energy` | Sativa, Hybrid | Energetic, Uplifted | Sleepy, Relaxed |
| "Help with anxiety" | `anxiety_relief` | Indica, Hybrid | Relaxed, Happy | Anxious, Paranoid |
| "Creative inspiration" | `creativity` | Sativa, Hybrid | Creative, Euphoric | Sleepy |

**Recent Improvements (v4.1):**
- Sleep queries now return multiple options (e.g., Northern Lights + OG Kush)  
- Energy queries include energizing Hybrids (e.g., Blue Dream + Sour Diesel)
- All filters expanded to include relevant Hybrid strains for better variety

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
- **Vector Search**: pgvector for efficient strain similarity search
- **Smart Caching**: Similar queries cached for faster responses
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

All ports are configurable via environment variables with sensible defaults.

## 🧪 Testing

### Automated Tests
```bash
# Run all tests
make test

# Tests include strain URL generation
python -m pytest tests/ -v
```

### Manual Testing
```bash
# Health check
curl http://localhost:8001/api/v1/ping/

# Strain search
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -d '{"message": "Best strain for creativity?"}'

# URL verification
curl http://localhost:8001/api/v1/strains/1 | jq '.url'
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
1. **Source**: Cannamente PostgreSQL (Spanish strain data)
2. **Sync**: Automatic data sync with change detection
3. **Processing**: Vector embeddings generation for strain search
4. **Storage**: Local PostgreSQL with pgvector
5. **API**: Multi-language strain recommendations with URLs

## 🗂 Project Structure

```
canagent/
├── app/                    # Application source code
│   ├── api/               # REST API endpoints
│   │   ├── chat.py       # 🆕 Context-Aware chat API with session support
│   │   ├── health.py     # Health checks and monitoring
│   │   └── strains.py    # Strain management API
│   ├── core/              # Core business logic
│   │   ├── session_manager.py       # 🆕 Redis session management with backup
│   │   ├── unified_processor.py     # 🆕 Single LLM call for complete analysis
│   │   ├── fallback_analyzer.py     # 🆕 Rule-based analyzer (no OpenAI needed)
│   │   ├── conflict_resolver.py     # 🆕 Criteria conflict detection & resolution
│   │   ├── adaptive_search.py       # 🆕 5-stage adaptive search with fallback
│   │   ├── optimized_rag_service.py # 🆕 Context-aware RAG service (main)
│   │   ├── intent_detection.py      # Intent detection and filtering rules
│   │   ├── rag_service.py          # Legacy RAG service (backup)
│   │   ├── llm_interface.py        # OpenAI/Mock interface
│   │   ├── cache.py                # Redis caching layer
│   │   └── metrics.py              # Prometheus metrics
│   ├── db/                # Database layer
│   │   ├── database.py   # Connection management + new models
│   │   └── repository.py # Enhanced repository with structured filtering
│   ├── models/            # Data models
│   │   ├── session.py    # 🆕 Session models (ConversationSession, UnifiedAnalysis)
│   │   ├── database.py   # SQLAlchemy models (Strain + Relations)
│   │   └── schemas.py    # 🆕 Extended Pydantic schemas (session_id, query_type, etc.)
│   └── utils/             # Utilities
│       └── data_import.py # Sample data utilities
├── tests/                 # Test suite
│   └── test_integration_dialog.py  # 🆕 Context-aware integration tests
├── scripts/               # Automation scripts
│   ├── sync_strain_relations.py  # Full sync with structured data (working script)
│   ├── init_database.py          # Production database initialization
│   ├── sync_daily.py             # Daily incremental synchronization
│   ├── common.py                 # Shared sync functions
│   └── init_pgvector.sql         # pgvector extension setup
├── docker-compose.yml     # 🆕 Docker configuration with Context-Aware env vars
├── env.example           # 🆕 Updated with Context-Aware Architecture settings
├── Dockerfile            # Container definition
├── Makefile              # Command automation
└── requirements.txt      # Python dependencies
```

## 🚀 Deployment Options

### Development
```bash
# Local development with mock responses
MOCK_MODE=true make start
```

### Staging
```bash
# Local development with real OpenAI API
MOCK_MODE=false make start
```

### Production
```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d
```

## 📝 Changelog

### 🚀 Current Version - v5.0 (Context-Aware Architecture v2.0) - LATEST
**🎯 MAJOR RELEASE: Conversational AI with Session Management**

- ✅ **Multi-step Conversations**: AI maintains context across questions in same session
- ✅ **Session Management**: 4-hour active sessions + 7-day preference backup via Redis  
- ✅ **Unified LLM Processing**: Single API call replaces 4-5 separate OpenAI requests
- ✅ **Rule-based Fallback**: Reliable operation even without OpenAI API access
- ✅ **Adaptive Search**: 5-stage fallback ensures no empty results (strict → relaxed → semantic → fallback)
- ✅ **Conflict Resolution**: Detects & resolves contradictory criteria with user warnings
- ✅ **Dynamic Quick Actions**: Context-aware UI suggestions based on conversation state
- ✅ **Quality Indicators**: Session restore, fallback mode, and confidence metrics
- ✅ **Enhanced API**: New fields - `session_id`, `query_type`, `language`, `confidence`, `quick_actions`, `warnings`
- ✅ **Frontend Integration Guide**: Complete JavaScript implementation for cannamente developers

**🎉 Problem Solved:**
- **Before**: "Which one is strongest?" → New search, loses context ❌
- **After**: "Which one is strongest?" → Compares previous recommendations ✅

### Previous Version - v4.1 (Enhanced Filtering & Stability) 
- 🔧 **SQL Fix**: Resolved critical PostgreSQL DISTINCT/ORDER BY conflict in vector similarity queries
- 🌿 **Better Sleep Recommendations**: Sleep queries now return multiple strains (Indica + appropriate Hybrids)
- ⚡ **Better Energy Recommendations**: Energy queries now include energizing Hybrid strains (not just Sativa)
- 📊 **More Variety**: All intent filters expanded to include relevant Hybrid strains for comprehensive results
- 🔍 **Improved Query Structure**: Database queries restructured for better performance and stability

### Legacy Version - v4.0 (Intent-Aware Intelligence)
- ✅ **Intent Detection**: Automatic detection of user needs (sleep/energy/focus/pain/anxiety)
- ✅ **Structured Filtering**: Never recommends conflicting strains (e.g., energizing sativas for sleep)
- ✅ **Rich Metadata**: Full strain effects, medical uses, flavors, and terpenes from cannamente
- ✅ **Enhanced Sync**: `make sync-enhanced` syncs all structured data automatically
- ✅ **Smart Recommendations**: 3-layer filtering (Intent → Structure → Vector)
- ✅ **Detailed Responses**: Includes detected intent and applied filters
- ✅ **Production Ready**: Automated sync, no manual database operations

### Major Problem Solved ✨
**Before**: "I need sleep" could return Sour Diesel (Sativa, Energetic, Talkative) ❌  
**After**: "I need sleep" returns Northern Lights (Indica, Sleepy, Relaxed) ✅

### Migration from v3.x
- **Enhanced API**: Responses now include `detected_intent` and `filters_applied`
- **New Scripts**: Use `init_database.py` for initialization, `sync_daily.py` for updates
- **Rich Data**: Strain responses include feelings, helps_with, negatives, flavors
- **Backwards Compatible**: All existing endpoints continue to work
- **New Configuration**: Added `CANNAMENTE_BASE_URL` and `STRAIN_URL_PATTERN`
- **Response Format**: `recommended_strains` with URLs instead of generic products
- **Database**: Strain-focused data model with full cannabis metadata

### Breaking Changes
- ❌ `/api/v1/products/` endpoint removed
- ❌ `recommended_products` field removed from chat responses
- ✅ Use `/api/v1/strains/` for browsing strains
- ✅ Use `recommended_strains` field in chat responses

---

## 🟢 Context-Aware Frontend Integration (Cannamente Developers)

### Session Management Implementation Required

To support the new Context-Aware Architecture v2.0, the cannamente frontend needs the following implementations:

#### 1. Enhanced Session Manager

```javascript
// Add to your chat component or app.js
class EnhancedSessionManager {
    constructor() {
        this.sessionId = this.getOrCreateSessionId();
        this.isRestored = false;
        this.language = null;
        this.lastActivity = Date.now();
    }
    
    getOrCreateSessionId() {
        let sessionId = sessionStorage.getItem('canagent_session_id');
        const lastActivity = sessionStorage.getItem('canagent_last_activity');
        
        // Check expiration (4 hours)
        if (sessionId && lastActivity) {
            const elapsed = Date.now() - parseInt(lastActivity);
            if (elapsed > 4 * 60 * 60 * 1000) {
                // Session expired but keep ID for restoration
                this.isRestored = true;
            }
        }
        
        if (!sessionId) {
            sessionId = this.generateUUID();
        }
        
        sessionStorage.setItem('canagent_session_id', sessionId);
        this.updateActivity();
        
        return sessionId;
    }
    
    updateActivity() {
        this.lastActivity = Date.now();
        sessionStorage.setItem('canagent_last_activity', this.lastActivity.toString());
    }
    
    reset() {
        // Soft reset - new ID but context preservation
        sessionStorage.setItem('canagent_session_id', this.generateUUID());
        this.updateActivity();
        this.isRestored = false;
    }
    
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }
}
```

#### 2. Updated API Calls

```javascript
// Modify your existing API calls to include session_id
async function sendMessage(message) {
    const response = await fetch('/api/v1/chat/ask/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            message: message,
            session_id: sessionManager.sessionId,     // ADD THIS
            history: getRecentHistory(),              // Your existing history
            source_platform: 'cannamente'            // ADD THIS
        })
    });
    
    const data = await response.json();
    
    // Handle context-aware response indicators
    if (data.is_restored) {
        showNotification('Conversación restaurada / Session restored');
    }
    
    if (data.is_fallback) {
        showNotification('Modo offline / Offline mode');
    }
    
    // Update session ID if changed
    if (data.session_id) {
        sessionManager.sessionId = data.session_id;
    }
    
    return data;
}
```

#### 3. Enhanced Response Handling

```javascript
// Handle new response fields from Context-Aware API
function renderResponse(response) {
    // Your existing rendering logic...
    
    // NEW: Handle query types for better UX
    switch (response.query_type) {
        case 'follow_up':
            renderFollowUpResponse(response);
            break;
        case 'comparison':
            renderComparisonResponse(response);
            break;
        case 'clarification':
            renderClarificationResponse(response);
            break;
        case 'reset':
            clearChatHistory();
            renderNewSearchResponse(response);
            break;
        default:
            renderStandardResponse(response);
    }
    
    // NEW: Show quick actions if available
    if (response.quick_actions?.length > 0) {
        renderQuickActions(response.quick_actions);
    }
    
    // NEW: Show quality indicators
    showQualityIndicators(response);
}

function renderQuickActions(actions) {
    const container = document.getElementById('quick-actions');
    container.innerHTML = actions.map(action => `
        <button class="quick-action-btn" onclick="sendMessage('${action}')">
            ${action}
        </button>
    `).join('');
}

function showQualityIndicators(response) {
    let indicators = [];
    
    if (response.is_restored) {
        indicators.push({type: 'info', text: 'Sesión restaurada'});
    }
    
    if (response.is_fallback) {
        indicators.push({type: 'warning', text: 'Modo básico'});
    }
    
    if (response.confidence < 0.7) {
        indicators.push({
            type: 'caution', 
            text: `Confianza: ${Math.round(response.confidence * 100)}%`
        });
    }
    
    if (response.warnings?.length > 0) {
        indicators.push({
            type: 'warning',
            text: `Conflictos resueltos: ${response.warnings.length}`
        });
    }
    
    // Render indicators in your UI
    renderIndicators(indicators);
}
```

#### 4. Reset Functionality

```javascript
// Add reset button to your chat UI
function resetConversation() {
    // Send reset command
    sendMessage('Empezar nueva búsqueda').then(response => {
        // Clear local chat history
        clearChatHistory();
        
        // Reset session manager
        sessionManager.reset();
        
        // Show fresh start message
        renderResponse(response);
    });
}

// Add button to your HTML
// <button onclick="resetConversation()">Nueva consulta</button>
```

#### 5. Multi-step Dialog Support

```javascript
// Your chat should now support follow-up questions
// Example conversation flow:

// User: "Necesito algo para dormir"
// Bot: Returns Indica strains + session_id

// User: "¿Cuál de estos es más fuerte?" 
// → API automatically uses session_id and works with previous recommendations

// User: "¿Hay algo más suave?"
// → API continues with same session context

// User: "Empezar nueva búsqueda" 
// → API resets context, starts fresh
```

### Integration Checklist for Cannamente Developers

**Required Changes:**
- [ ] ✅ **Session Management**: Implement `EnhancedSessionManager` class
- [ ] ✅ **API Updates**: Add `session_id` and `source_platform` to API calls  
- [ ] ✅ **Response Handling**: Handle new fields (`query_type`, `quick_actions`, `is_restored`, `is_fallback`, `warnings`)
- [ ] ✅ **Reset Button**: Add "Nueva consulta" button with reset functionality
- [ ] ✅ **Quality Indicators**: Show session status and confidence indicators
- [ ] ✅ **Quick Actions**: Render and handle dynamic quick action buttons

**Optional Enhancements:**
- [ ] 🔄 **Typing Indicators**: Show when AI is thinking vs fallback mode
- [ ] 🎯 **Smart Suggestions**: Use `quick_actions` for auto-complete
- [ ] 📊 **Analytics**: Track session lengths and success rates
- [ ] 🌐 **Language Switching**: Handle language changes within same session

### Benefits for Cannamente Users

✅ **Better Conversations**: "¿Cuál es mejor?" works without repeating context  
✅ **Smart Memory**: AI remembers previous recommendations in same session  
✅ **Language Flexibility**: Switch between Spanish/English mid-conversation  
✅ **Conflict Resolution**: "Algo relajante pero energético" → AI resolves contradictions  
✅ **Session Recovery**: Restore context after brief disconnections  
✅ **Offline Fallback**: Basic functionality even when OpenAI is unavailable  

### Configuration

```env
# Ensure Context-Aware Architecture is enabled
USE_CONTEXTUAL_RAG=true
SESSION_TTL_HOURS=4
SESSION_BACKUP_DAYS=7
```

---

## 🎯 Ready to Use!

**Quick start:** `make start` and begin making API calls to get strain recommendations with URLs.

**Integration:** Configure your cannamente domain and start receiving clickable strain links.

**Documentation:** All endpoints documented with examples above.

**Support:** Check logs with `make logs` or status with `make status`.

**Community:** This is a modern, production-ready AI strain recommendation system with seamless cannamente integration. 🌿