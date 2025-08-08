# Cannamente - AI Cannabis Strain Recommendation System

🌿 **Smart cannabis strain recommendations using RAG (Retrieval-Augmented Generation) and vector search.**

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
# Edit OPENAI_API_KEY and other settings
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

### English Query
```bash
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What do you recommend for creativity and focus?", "history": []}'
```

### Spanish Query (cannamente style)
```bash
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué me recomiendas para creatividad y concentración?", "history": []}'
```

## ⚙️ Configuration

### Environment Variables

**Production Setup:**
```env
# OpenAI API
OPENAI_API_KEY=your_actual_api_key_here
MOCK_MODE=false                    # Use real OpenAI API

# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=ai_budtender
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password

# Redis Caching
REDIS_HOST=redis
REDIS_PORT=6379

# Performance
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

**Development Setup:**
```env
# OpenAI API (Development)
MOCK_MODE=true                     # Use mock responses (saves API costs)

# Other settings same as production
```

### Mock Mode vs Real API

| Mode | Use Case | Cost | Response Quality |
|------|----------|------|------------------|
| `MOCK_MODE=true` | Development, testing | Free | Good mock responses |
| `MOCK_MODE=false` | Production, real usage | OpenAI API costs | Best AI responses |

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
make shell           # Container shell access
make redis-cli       # Redis CLI access
```

### Data Management
```bash
make sync-cannamente    # Sync all data from cannamente
make sync-new           # Sync only new data
make watch-cannamente   # Auto-monitor for changes
```

### Development
```bash
make test            # Run tests
make build          # Build Docker images
make clean          # Clean containers and volumes
```

## 🏗 Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Cannamente    │    │   AI Budtender   │    │     Client      │
│   (Source DB)   │───▶│   (Local API)    │───▶│   (Frontend)    │
│                 │    │                  │    │                 │
│ - Spanish data  │    │ - Vector search  │    │ - Multi-language│
│ - READ ONLY     │    │ - OpenAI/Mock    │    │ - Real-time API │
│ - PostgreSQL    │    │ - Redis cache    │    │ - JSON responses│
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Features:**
- ✅ Local PostgreSQL with pgvector (fast vector search)
- ✅ Real OpenAI API integration with mock mode fallback
- ✅ Redis caching for performance
- ✅ Prometheus metrics monitoring
- ✅ Multi-language support (English/Spanish)
- ✅ Production-ready with health checks

## 🌐 API Endpoints

### Health & Status
```bash
# Health check
curl http://localhost:8001/api/v1/ping/

# Metrics (Prometheus format)
curl http://localhost:8001/metrics

# Cache statistics
curl http://localhost:8001/api/v1/cache/stats/
```

### Chat API
```bash
# English recommendation
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I need something for relaxation after work",
    "history": []
  }'

# Spanish recommendation (cannamente style)
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Necesito algo para relajarme después del trabajo",
    "history": []
  }'
```

### Product Management
```bash
# List all products
curl http://localhost:8001/api/v1/products/

# Get specific product
curl http://localhost:8001/api/v1/products/1

# Create new product (for testing)
curl -X POST http://localhost:8001/api/v1/products/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Strain",
    "description": "Test description"
  }'
```

### Cache Management
```bash
# View cache stats
curl http://localhost:8001/api/v1/cache/stats/

# Clear cache
curl -X POST http://localhost:8001/api/v1/cache/clear/
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

# Cache performance
curl http://localhost:8001/api/v1/cache/stats/

# Database health
make check-db
```

### Performance Optimization
- **Redis Caching**: Similar queries cached for faster responses
- **Vector Search**: pgvector for efficient similarity search
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

# Check test coverage
make test-coverage
```

### Manual Testing
```bash
# Health check
curl http://localhost:8001/api/v1/ping/

# English query
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Best strain for creativity?", "history": []}'

# Spanish query
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Mejor cepa para creatividad?", "history": []}'
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
- [ ] Configure rate limits for your use case
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
1. **Source**: Cannamente PostgreSQL (Spanish data)
2. **Sync**: Automatic data sync with change detection
3. **Processing**: Vector embeddings generation
4. **Storage**: Local PostgreSQL with pgvector
5. **API**: Multi-language recommendations

## 🗂 Project Structure

```
cannamente/
├── app/                    # Application source code
│   ├── api/               # REST API endpoints
│   │   ├── chat.py       # Chat/recommendation API
│   │   ├── health.py     # Health checks
│   │   └── products.py   # Product management
│   ├── core/              # Core business logic
│   │   ├── llm_interface.py  # OpenAI/Mock interface
│   │   ├── rag_service.py    # RAG implementation
│   │   ├── cache.py          # Redis caching
│   │   └── metrics.py        # Prometheus metrics
│   ├── db/                # Database layer
│   │   ├── database.py   # Connection management
│   │   └── repository.py # Data access layer
│   ├── models/            # Data models
│   │   ├── database.py   # SQLAlchemy models
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

### Current Version - v2.0
- ✅ **Multi-language**: English (primary) + Spanish support
- ✅ **Real AI Integration**: OpenAI API with mock mode fallback
- ✅ **Performance**: Redis caching, async operations
- ✅ **Monitoring**: Prometheus metrics, structured logging
- ✅ **Production Ready**: Health checks, rate limiting
- ✅ **Data Sync**: Automatic cannamente integration
- ✅ **Developer Experience**: Simple commands, comprehensive docs

### Migration from v1.x
- Project renamed from `ai_budtender` to `cannamente`
- Added `MOCK_MODE` configuration
- Improved multi-language support
- Enhanced monitoring and caching

---

## 🎯 Ready to Use!

**Quick start:** `make start` and begin making API calls.

**Documentation:** All endpoints documented with examples above.

**Support:** Check logs with `make logs` or status with `make status`.

**Community:** This is a modern, production-ready AI recommendation system. 🌿