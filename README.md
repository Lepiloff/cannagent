# Canagent - AI Cannabis Strain Recommendation System

🌿 **Smart cannabis strain recommendations using Intent Detection + RAG (Retrieval-Augmented Generation) with structured filtering for accurate, context-aware recommendations.**

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

### Strain Recommendations
```bash
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for relaxation and sleep", "history": []}'
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
      "url": "http://localhost:8001/strain/northern-lights/",
      "feelings": [{"name": "Sleepy", "energy_type": "relaxing"}],
      "helps_with": [{"name": "Insomnia"}],
      "negatives": [{"name": "Dry mouth"}],
      "flavors": [{"name": "earthy"}]
    }
  ],
  "detected_intent": "sleep",
  "filters_applied": {
    "preferred_categories": ["Indica"],
    "exclude_feelings": ["Energetic", "Talkative"]
  }
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
# Spanish Query (cannamente style)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué me recomiendas para creatividad y concentración?", "history": []}'
```

## ⚙️ Configuration

### Environment Variables

**Cannamente Integration:**
```env
# Cannamente URL Configuration
CANNAMENTE_BASE_URL=http://localhost:8001
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
```

### URL Configuration

The system generates clickable strain URLs for cannamente integration:

| Setting | Description | Example |
|---------|-------------|---------|
| `CANNAMENTE_BASE_URL` | Base URL for strain pages | `http://localhost:8001` |
| `STRAIN_URL_PATTERN` | URL pattern with slug | `/strain/{slug}/` |
| **Result** | Generated strain URL | `http://localhost:8001/strain/blue-dream/` |

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

## 🏗 Enhanced Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Cannamente    │    │   Canagent       │    │   Client App    │
│   (Source DB)   │───▶│   (AI API)       │───▶│   (Frontend)    │
│                 │    │                  │    │                 │
│ - Strain data   │    │ 🧠 Intent Detection │    │ - Strain URLs   │
│ - Feelings      │    │ 🔍 Structured Filter │    │ - Smart Results │
│ - Medical uses  │    │ 🔗 Vector Search    │    │ - Intent Info   │
│ - Effects       │    │ 🤖 OpenAI/Mock     │    │ - JSON responses│
│ - PostgreSQL    │    │ 💾 Redis cache     │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 🎯 Smart Recommendation Flow:
1. **Intent Detection**: "I need sleep" → `IntentType.SLEEP`
2. **Structured Filtering**: Prefer Indica, Require Sleepy/Relaxed, Exclude Energetic  
3. **Vector Search**: Semantic similarity within filtered results
4. **AI Response**: Context-aware explanation with pre-filtered strains

**Key Features:**
- ✅ **Intent-Aware**: Automatic detection of user needs (sleep/energy/focus/pain)
- ✅ **Structured Filtering**: Never recommends conflicting strains (e.g., energizing sativas for sleep)
- ✅ **Rich Metadata**: Full strain effects, medical uses, flavors, and terpenes
- ✅ **Vector Search**: pgvector for semantic strain matching within filtered results
- ✅ **Real AI Integration**: OpenAI API with intelligent mock mode fallback
- ✅ **Multi-language**: English/Spanish support with intent detection
- ✅ **Production Ready**: Health checks, rate limiting, monitoring, automated sync

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
      "url": "http://localhost:8001/strain/northern-lights/",
      
      // Effects and characteristics (arrays of objects)
      "feelings": [
        {"name": "Sleepy", "energy_type": "relaxing"},
        {"name": "Relaxed", "energy_type": "relaxing"}
      ],
      "helps_with": [
        {"name": "Insomnia"},
        {"name": "Stress"}
      ],
      "negatives": [
        {"name": "Dry mouth"},
        {"name": "Dry eyes"}
      ],
      "flavors": [
        {"name": "earthy"},
        {"name": "pine"}
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
| `url` | string/null | Direct link to strain page | `"http://localhost:8001/strain/northern-lights/"` | ❌ |
| `feelings` | array | Effects/sensations | `[{"name": "Sleepy", "energy_type": "relaxing"}]` | ✅ |
| `helps_with` | array | Medical uses/conditions | `[{"name": "Insomnia"}]` | ✅ |
| `negatives` | array | Side effects | `[{"name": "Dry mouth"}]` | ✅ |
| `flavors` | array | Taste/aroma profiles | `[{"name": "earthy"}]` | ✅ |

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
│   │   ├── chat.py       # Enhanced chat API with intent detection
│   │   ├── health.py     # Health checks and monitoring
│   │   └── strains.py    # Strain management API
│   ├── core/              # Core business logic
│   │   ├── intent_detection.py # Intent detection and filtering rules
│   │   ├── rag_service.py      # Enhanced RAG with structured filtering
│   │   ├── llm_interface.py    # OpenAI/Mock interface
│   │   ├── cache.py            # Redis caching layer
│   │   └── metrics.py          # Prometheus metrics
│   ├── db/                # Database layer
│   │   ├── database.py   # Connection management + new models
│   │   └── repository.py # Enhanced repository with structured filtering
│   ├── models/            # Data models
│   │   ├── database.py   # SQLAlchemy models (Strain + Relations)
│   │   └── schemas.py    # Pydantic schemas with structured data
│   └── utils/             # Utilities
│       └── data_import.py # Sample data utilities
├── tests/                 # Test suite
├── scripts/               # Automation scripts
│   ├── sync_strain_relations.py  # Full sync with structured data (working script)
│   ├── init_database.py          # Production database initialization
│   ├── sync_daily.py             # Daily incremental synchronization
│   ├── common.py                 # Shared sync functions
│   └── init_pgvector.sql         # pgvector extension setup
├── docker-compose.yml     # Docker configuration
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

### Latest Updates - v4.1 (Enhanced Filtering & Stability)
- 🔧 **SQL Fix**: Resolved critical PostgreSQL DISTINCT/ORDER BY conflict in vector similarity queries
- 🌿 **Better Sleep Recommendations**: Sleep queries now return multiple strains (Indica + appropriate Hybrids)
- ⚡ **Better Energy Recommendations**: Energy queries now include energizing Hybrid strains (not just Sativa)
- 📊 **More Variety**: All intent filters expanded to include relevant Hybrid strains for comprehensive results
- 🔍 **Improved Query Structure**: Database queries restructured for better performance and stability

### Current Version - v4.0 (Intent-Aware Intelligence)
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

## 🎯 Ready to Use!

**Quick start:** `make start` and begin making API calls to get strain recommendations with URLs.

**Integration:** Configure your cannamente domain and start receiving clickable strain links.

**Documentation:** All endpoints documented with examples above.

**Support:** Check logs with `make logs` or status with `make status`.

**Community:** This is a modern, production-ready AI strain recommendation system with seamless cannamente integration. 🌿