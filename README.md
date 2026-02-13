# AI Budtender 🌿

Cannabis strain recommendation system with AI-powered query analysis, fuzzy matching, and vector search.

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenAI API key (or use MOCK_MODE=true)

### Setup
```bash
# 1. Configure environment
cp env.example .env
# Edit OPENAI_API_KEY and other settings in .env

# 2. Start services
docker compose up -d

# 3. Sync strain data
docker compose exec api python scripts/sync_strain_relations.py

# 4. Test the API
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for sleep"}'
```

### Daily Operations
```bash
# Start/stop services
docker compose up -d
docker compose down

# View logs
docker compose logs -f api

# Update strain data
docker compose exec api python scripts/sync_strain_relations.py
```

## Architecture

**Current System:**
- **Async Processing**: Main service with granular concurrency
- **Session Management**: Redis-backed conversations (4h TTL)
- **Fuzzy Matching**: PostgreSQL pg_trgm for typo tolerance
- **Vector Search**: Pre-computed embeddings with semantic ranking
- **Bilingual Support**: English/Spanish with language detection

**Query Flow:**
1. LLM analyzes user query (intent, criteria extraction)
2. SQL pre-filtering (category, THC/CBD ranges)
3. Attribute filtering with fuzzy matching (flavors, effects, medical uses)
4. Vector search for semantic similarity ranking
5. Natural language response generation

## API Usage

### Basic Strain Search
```bash
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "suggest indica with high THC for sleep"}'
```

### Bilingual Support
```bash
# Spanish
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Necesito algo para el dolor con alto CBD"}'

# English
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need something for pain with high CBD"}'
```

### Health Check
```bash
curl http://localhost:8001/health/
```

## Documentation

- **[API.md](API.md)** - Complete API documentation with schemas
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Setup, testing, and troubleshooting
- **[STREAMLINED_RAG_ARCHITECTURE.md](STREAMLINED_RAG_ARCHITECTURE.md)** - Technical architecture details
- **[CLAUDE.md](CLAUDE.md)** - Guidelines for Claude AI development

## Environment Configuration

**Required:**
```env
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://user:password@db:5432/ai_budtender
REDIS_HOST=redis
```

**Optional:**
```env
MOCK_MODE=true           # Use mock responses for development
SESSION_TTL=14400        # 4 hours
RATE_LIMIT_ENABLED=true  # API rate limiting
LOG_LEVEL=INFO
```

## Services & Ports

| Service | Port | Purpose |
|---------|------|---------|
| API | 8001 | Main application |
| Database | 5433 | PostgreSQL with pgvector |
| Redis | 6380 | Session storage |
| Metrics | 9091 | Prometheus metrics |

## Testing

```bash
# Run all tests
docker compose exec api pytest tests/ -v

# Test API functionality
docker compose exec api python -c "
import requests
response = requests.post(
    'http://localhost:8001/api/v1/chat/ask',
    json={'message': 'test query'}
)
print(f'Status: {response.status_code}')
print(f'Response: {response.json()}')
"
```

## Data Management

### Sync Strain Data
```bash
# Full sync from cannamente database
docker compose exec api python scripts/sync_strain_relations.py

# Production database initialization
docker compose exec api python scripts/init_database.py

# Daily incremental updates
docker compose exec api python scripts/sync_daily.py
```

### Database Health
```bash
# Check strain count
docker compose exec api python -c "
from app.db.database import SessionLocal
from app.db.repository import StrainRepository
db = SessionLocal()
repo = StrainRepository(db)
strains = repo.get_strains(limit=5)
print(f'Available strains: {len(strains)}')
for strain in strains:
    print(f'  - {strain.name} ({strain.category})')
db.close()
"
```

## Production Deployment

1. **Environment Setup**: Configure production environment variables
2. **Database Migration**: `docker compose exec api alembic upgrade head`
3. **Data Sync**: Initial population with `scripts/init_database.py`
4. **Monitoring**: Health checks on `/health/` and metrics on `:9091/metrics`
5. **Backup**: Regular PostgreSQL backups and Redis session data

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed production setup instructions.

## Key Features

✅ **Smart Query Analysis** - AI-powered intent detection and criteria extraction
✅ **Fuzzy Matching** - Handles typos with PostgreSQL trigram similarity
✅ **Vector Search** - Semantic similarity ranking with pre-computed embeddings
✅ **Session Context** - Conversation continuity with Redis storage
✅ **Bilingual Support** - English/Spanish with automatic language detection
✅ **Medical Safety** - Appropriate strain recommendations based on medical needs
✅ **Async Processing** - Non-blocking pipeline with dedicated thread pools
✅ **Production Ready** - Rate limiting, monitoring, health checks, structured logging

## Contributing

1. Follow existing code patterns and async architecture
2. Add tests for new functionality
3. Update relevant documentation files
4. Ensure all existing tests pass: `docker compose exec api pytest tests/ -v`

## Support

- **Logs**: `docker compose logs -f api`
- **Health**: `curl http://localhost:8001/health/`
- **Issues**: Check logs first, then review DEPLOYMENT.md troubleshooting section

---

**License**: Private project for cannamente integration
**Status**: Production ready with async processing pipeline