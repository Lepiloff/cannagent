# AI Budtender - Smart Cannabis Product Selection Assistant

## Description

AI Budtender is a local prototype of a cloud service that provides an intelligent chatbot for cannabis product e-commerce websites. The bot helps users with product selection, answers questions about products and makes recommendations based on vector search (RAG).

**⚠️ Important**: This project is configured to use an external database from the **cannamente** project. Make sure the cannamente database is running before starting this service.

## Architecture Options

### Option 1: Local Database (Recommended for Development)

**Advantages:**
- ✅ Full control over database and pgvector
- ✅ No dependency on external services
- ✅ Vector data persists across restarts
- ✅ Simulates production architecture
- ✅ Data sync from client database (cannamente)

**How it works:**
1. **Local PostgreSQL** with pgvector extension
2. **Data sync** from cannamente (simulates client DB)
3. **Vector search** on local database
4. **AI processing** with cached embeddings

### Option 2: External Database (Current)

**Advantages:**
- ✅ Shared data with cannamente
- ✅ No data duplication
- ✅ Real-time updates

**Disadvantages:**
- ❌ pgvector needs reinstallation after restart
- ❌ Dependency on external service
- ❌ Vector data management complexity

## Quick Start

### Option 1: Local Database (Recommended)

```bash
# Complete setup with local database
make setup-local

# Or step by step:
make start-local
make sync-cannamente
```

### Option 2: External Database

```bash
# Start with external cannamente database
make start
make setup-pgvector  # After restart
```

## Technologies

- **Backend**: Python 3.11+, FastAPI
- **Database**: PostgreSQL with pgvector extension
- **AI/ML**: LangChain, OpenAI API (with mock mode support)
- **Vector Search**: pgvector for semantic search
- **Containerization**: Docker, Docker Compose
- **Testing**: Pytest, FastAPI TestClient
- **Caching**: Redis for embeddings and responses
- **Monitoring**: Prometheus metrics
- **Rate Limiting**: SlowAPI for request throttling
- **Logging**: Structured logging with JSON format
- **Migrations**: Alembic for database versioning

## Prerequisites

### For Local Database (Recommended)

1. **Docker and Docker Compose** installed
2. **Cannamente project** running (for data sync)
3. **Python 3.11+** for sync scripts

### For External Database

1. **Cannamente project** must be running
2. **PostgreSQL** with pgvector extension
3. **Docker and Docker Compose** installed

## Environment Setup

### Local Database Configuration

```env
# Local Database
DATABASE_URL=postgresql://ai_user:ai_password@db:5432/ai_budtender
POSTGRES_DB=ai_budtender
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

# OpenAI (optional)
OPENAI_API_KEY=your_openai_api_key_here

# Mock Mode (true to work without OpenAI)
MOCK_MODE=true

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60
```

### External Database Configuration

```env
# External Database (cannamente project)
DATABASE_URL=postgresql://myuser:mypassword@host-gateway:5432/mydatabase
POSTGRES_DB=mydatabase
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_HOST=host-gateway
POSTGRES_PORT=5432
```

## Port Configuration

| Service | Local DB Port | External DB Port | Reason |
|---------|---------------|------------------|---------|
| API | 8001 | 8001 | Avoid conflict with cannamente web |
| Metrics | 9091 | 9091 | Avoid potential conflicts |
| Redis | 6380 | 6380 | Avoid potential conflicts |
| PostgreSQL | 5433 | 5432 | Local vs external |

## Daily Usage Commands

### Local Database (Recommended)

```bash
# Complete setup
make setup-local

# Start services
make start-local

# Stop services
make stop-local

# Sync data from cannamente
make sync-cannamente

# Check status
make status
```

### External Database

```bash
# Start services
make start

# Setup pgvector after restart
make setup-pgvector

# Stop services
make stop

# Check status
make status
```

### Common Commands

```bash
# Check database connection
make check-db

# Show logs
make logs

# Run tests
make test

# Open shell in container
make shell
```

## API Usage Examples

### 1. Health Check

```bash
# Basic health check
curl -s http://localhost:8001/api/v1/ping/ | python3 -m json.tool

# Expected response:
{
    "status": "ok",
    "database": "ok", 
    "redis": "connected",
    "timestamp": "2025-07-18T18:35:16.905091"
}
```

### 2. Get All Products

```bash
# Get all products
curl -s http://localhost:8001/api/v1/products/ | python3 -m json.tool

# Expected response:
{
    "products": [
        {
            "id": 1,
            "name": "Blue Dream",
            "description": "Sativa-Indica hybrid for daytime use",
            "created_at": "2024-01-01T12:00:00Z"
        }
    ]
}
```

### 3. Create New Product

```bash
# Create a new product
curl -X POST http://localhost:8001/api/v1/products/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Northern Lights",
    "description": "Classic indica strain for evening relaxation"
  }' | python3 -m json.tool

# Expected response:
{
    "id": 2,
    "name": "Northern Lights", 
    "description": "Classic indica strain for evening relaxation",
    "created_at": "2024-01-01T12:00:00Z"
}
```

### 4. Chat with AI Budtender

```bash
# Ask for recommendations
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I need something for evening relaxation",
    "history": []
  }' | python3 -m json.tool

# Expected response:
{
    "response": "For evening relaxation, I recommend Northern Lights...",
    "recommended_products": [
        {
            "id": 2,
            "name": "Northern Lights",
            "description": "Classic indica strain for evening relaxation",
            "created_at": "2024-01-01T12:00:00Z"
        }
    ]
}
```

### 5. Cache Management

```bash
# Get cache statistics
curl -s http://localhost:8001/api/v1/cache/stats/ | python3 -m json.tool

# Clear cache
curl -X POST http://localhost:8001/api/v1/cache/clear/ | python3 -m json.tool
```

### 6. Metrics

```bash
# Get Prometheus metrics
curl -s http://localhost:8001/metrics
```

### 7. API Documentation

```bash
# Open in browser
open http://localhost:8001/api/v1/docs
```

## Complete Makefile Commands

```bash
# Help - show all available commands
make help

# Local Database (Recommended)
make setup-local      # Complete local setup
make start-local      # Start with local DB
make stop-local       # Stop local services
make sync-cannamente  # Sync data from cannamente

# External Database
make start            # Start with external DB
make setup-pgvector   # Setup pgvector after restart

# Common Commands
make build
make restart
make logs
make status

# Database operations
make init-pgvector
make check-db
make migration MSG="add new field"

# Development
make test
make shell
make redis-cli

# Maintenance
make clean
make install
make dev

# Code quality
make format
make lint
make security

# Dependencies
make freeze
```

## How It Works

### Local Database Architecture

1. **Data Sync**: Script reads from cannamente (client DB)
2. **Local Storage**: Data stored in local PostgreSQL with pgvector
3. **Vector Search**: Fast semantic search on local database
4. **AI Processing**: LLM generates responses based on local data
5. **Caching**: Redis caches embeddings and responses

### External Database Architecture

1. **Direct Access**: API directly queries cannamente database
2. **Vector Search**: Uses pgvector in external database
3. **AI Processing**: LLM processes data from external source
4. **Caching**: Redis caches for performance

### 1. Request Flow

1. **User sends question** via `/api/v1/chat/ask/` endpoint
2. **System generates embedding** for the user's question using OpenAI or mock mode
3. **Vector search** finds similar products in the database using pgvector
4. **Context preparation** combines user question with relevant product data
5. **LLM processing** generates personalized response using OpenAI or mock LLM
6. **Response formatting** includes both text response and recommended products
7. **Caching** stores embeddings and responses in Redis for future use

### 2. Vector Search Process

- Uses pgvector extension for semantic similarity search
- Searches through product descriptions and names
- Returns top-k most similar products
- Combines with traditional keyword search for better results

### 3. Caching Strategy

- **Embedding cache**: Stores generated embeddings to avoid re-computation
- **Response cache**: Caches AI responses for identical queries
- **Product cache**: Caches frequently accessed product data
- **TTL-based expiration**: Automatic cleanup of old cache entries

### 4. Rate Limiting

- **API endpoints**: 100 requests per minute per IP
- **Health endpoints**: 10 requests per minute
- **Cache operations**: 5 requests per minute
- **Configurable limits** via environment variables

## Architecture

```
ai_budtender/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── api/                 # API endpoints
│   │   ├── chat.py          # Chat with AI
│   │   ├── health.py        # Health check & cache
│   │   └── products.py      # Product management
│   ├── core/                # Business logic
│   │   ├── llm_interface.py # LLM abstraction
│   │   ├── rag_service.py   # RAG logic
│   │   ├── cache.py         # Redis caching
│   │   ├── logging.py       # Structured logging
│   │   ├── metrics.py       # Prometheus metrics
│   │   └── rate_limiter.py  # Rate limiting
│   ├── db/                  # Database operations
│   │   ├── database.py      # Database connection
│   │   ├── async_database.py # Async database
│   │   └── repository.py    # Product repository
│   ├── models/              # Data models
│   │   ├── database.py      # SQLAlchemy models
│   │   └── schemas.py       # Pydantic schemas
│   └── utils/               # Utilities
│       └── data_import.py   # Data import
├── alembic/                 # Database migrations
│   ├── versions/            # Migration files
│   └── env.py              # Alembic environment
├── scripts/                 # Utility scripts
│   ├── init_db.py          # Database initialization
│   ├── init_pgvector.py    # pgvector initialization
│   └── sync_cannamente.py  # Data sync from cannamente
├── tests/                   # Tests
├── docker-compose.yml       # Docker configuration (external DB)
├── docker-compose-local.yml # Docker configuration (local DB)
├── Dockerfile              # Docker image
├── Makefile                # Development commands
├── alembic.ini             # Alembic configuration
└── requirements.txt        # Dependencies
```

## Troubleshooting

### Local Database Issues

1. **Database not starting**:
   ```bash
   make stop-local
   docker-compose -f docker-compose-local.yml up -d
   ```

2. **Sync issues**:
   ```bash
   make sync-cannamente
   ```

3. **Check local database**:
   ```bash
   docker exec -it ai_budtender-db-1 psql -U ai_user -d ai_budtender
   ```

### External Database Issues

1. **Check if cannamente is running**:
   ```bash
   docker ps | grep canna
   ```

2. **Verify database connection**:
   ```bash
   make check-db
   ```

3. **Initialize pgvector if needed**:
   ```bash
   make init-pgvector
   ```

### Port Conflicts

If you encounter port conflicts:

1. Check if cannamente is using the same ports
2. Modify ports in `docker-compose.yml` if needed
3. Restart services: `make restart`

### Service Won't Start

1. **Check logs**:
   ```bash
   make logs
   ```

2. **Verify environment**:
   ```bash
   cat .env
   ```

3. **Rebuild containers**:
   ```bash
   make clean
   make build
   make start
   ```

## Production Architecture

### Recommended Production Setup

1. **AWS RDS** with pgvector extension
2. **Data sync** from client databases via API
3. **Redis ElastiCache** for caching
4. **ECS/Fargate** for container orchestration
5. **API Gateway** for request routing

### Data Flow in Production

```
Client Database → API Sync → AI Budtender DB → Vector Search → AI Response
```

## Security Considerations

1. **Rate limiting** prevents abuse
2. **Input validation** on all endpoints
3. **Environment variables** for sensitive data
4. **Docker security** best practices
5. **Regular updates** of dependencies

## Contributing

1. **Fork the repository**
2. **Create feature branch**
3. **Make changes**
4. **Run tests**: `make test`
5. **Submit pull request**

## License

This project is for educational and research purposes only. 