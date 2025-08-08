# Canagent - AI Cannabis Strain Recommendation System

🌿 **Smart cannabis strain recommendations using RAG (Retrieval-Augmented Generation) and vector search with configurable URLs for seamless cannamente integration.**

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
make sync-cannamente    # sync data from cannamente
make check-db          # verify DB connection
make logs             # view logs

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

3. **Sync data from cannamente:**
```bash
make sync-cannamente
```

## 🎯 API Usage Examples

### Strain Recommendations
```bash
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for relaxation and sleep", "history": []}'
```

**Response includes strain URLs:**
```json
{
  "response": "I recommend Northern Lights for relaxation...",
  "recommended_strains": [
    {
      "name": "Northern Lights",
      "category": "Indica", 
      "thc": "18.50",
      "cbd": "0.10",
      "slug": "northern-lights",
      "url": "http://localhost:8000/strain/northern-lights/",
      "description": "Classic indica strain. Strong relaxing effect..."
    }
  ]
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
CANNAMENTE_BASE_URL=http://localhost:8000
STRAIN_URL_PATTERN=/strain/{slug}/

# Database (External cannamente database)
DATABASE_URL=postgresql://myuser:mypassword@host-gateway:5432/mydatabase
POSTGRES_HOST=host-gateway
POSTGRES_PORT=5432
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

## 🛠 Commands

### Core Operations
```bash
make start           # Start all services
make stop            # Stop services  
make restart         # Restart everything
make logs            # Real-time logs
```

### Monitoring & Health
```bash
make check-db        # Check database connection
make status          # Service status
make test            # Run tests
```

### Data Management
```bash
make sync-cannamente    # Sync all data from cannamente
make sync-new           # Sync only new data
make watch-cannamente   # Auto-monitor for changes
```

## 🏗 Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Cannamente    │    │   Canagent       │    │   Client App    │
│   (Source DB)   │───▶│   (AI API)       │───▶│   (Frontend)    │
│                 │    │                  │    │                 │
│ - Spanish data  │    │ - Vector search  │    │ - Strain URLs   │
│ - READ ONLY     │    │ - OpenAI/Mock    │    │ - Recommendations│
│ - PostgreSQL    │    │ - Redis cache    │    │ - JSON responses│
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Key Features:**
- ✅ **Strain-focused**: Cannabis strain recommendations with full metadata
- ✅ **Configurable URLs**: Dynamic strain page links for any domain
- ✅ **Vector Search**: pgvector for semantic strain matching
- ✅ **Real AI Integration**: OpenAI API with mock mode fallback
- ✅ **Multi-language**: English/Spanish support
- ✅ **Production Ready**: Health checks, rate limiting, monitoring

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

### Chat API
```bash
# Get strain recommendations
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What strains are best for creativity and focus?",
    "history": []
  }'

# Follow-up conversation
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Which has higher THC?",
    "history": ["What strains are best for creativity?", "I recommend Sour Diesel and Green Crack..."]
  }'
```

### Response Format
```json
{
  "response": "Based on your needs, I recommend these strains...",
  "recommended_strains": [
    {
      "id": 3,
      "name": "Sour Diesel",
      "title": "Sour Diesel - Energizing Sativa",
      "category": "Sativa",
      "thc": "20.00",
      "cbd": "0.10", 
      "description": "Energetic sativa. Provides invigorating and creative effects.",
      "slug": "sour-diesel",
      "url": "http://localhost:8000/strain/sour-diesel/",
      "active": true,
      "created_at": "2025-08-08T16:33:27.257901"
    }
  ]
}
```

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

| Service | Port | Purpose |
|---------|------|---------|
| API Server | 8001 | Main application |
| Metrics | 9091 | Prometheus metrics |
| Redis | 6380 | Caching layer |
| Local DB | 5433 | Application database |
| Cannamente DB | 5432 | Source data (external) |

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

### Automatic Sync
```bash
# One-time sync from cannamente
make sync-cannamente

# Continuous monitoring (every 30 seconds)
make watch-cannamente

# Background monitoring
nohup make watch-cannamente > sync.log 2>&1 &
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
│   │   ├── chat.py       # Chat/recommendation API
│   │   ├── health.py     # Health checks
│   │   └── strains.py    # Strain management API
│   ├── core/              # Core business logic
│   │   ├── llm_interface.py  # OpenAI/Mock interface
│   │   ├── rag_service.py    # RAG implementation for strains
│   │   ├── cache.py          # Redis caching
│   │   └── metrics.py        # Prometheus metrics
│   ├── db/                # Database layer
│   │   ├── database.py   # Connection management
│   │   └── repository.py # Data access layer (strains + legacy products)
│   ├── models/            # Data models
│   │   ├── database.py   # SQLAlchemy models (Strain model)
│   │   └── schemas.py    # Pydantic schemas
│   └── utils/             # Utilities
│       └── data_import.py # Data sync utilities
├── tests/                 # Test suite
├── scripts/               # Automation scripts
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

### Current Version - v3.0 (Strain-focused)
- ✅ **Strain-centric**: Focus on cannabis strain recommendations vs generic products
- ✅ **Configurable URLs**: Dynamic strain page links for any cannamente domain
- ✅ **Enhanced API**: `/api/v1/strains/` endpoint with full strain metadata
- ✅ **Improved RAG**: Strain-specific semantic search and recommendations
- ✅ **Clean Architecture**: Removed legacy product code
- ✅ **URL Integration**: Seamless linking to cannamente strain pages

### Migration from v2.x
- **API Changes**: `/products/` API removed, use `/strains/` instead
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