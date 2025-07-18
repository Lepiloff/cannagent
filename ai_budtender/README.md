# AI Budtender - Smart Cannabis Product Selection Assistant

## Description

AI Budtender is a local prototype of a cloud service that provides an intelligent chatbot for cannabis product e-commerce websites. The bot helps users with product selection, answers questions about products and makes recommendations based on vector search (RAG).

**⚠️ Important**: This project is configured to use an external database from the **cannamente** project. Make sure the cannamente database is running before starting this service.

## Technologies

- **Backend**: Python 3.11+, FastAPI
- **Database**: External PostgreSQL from cannamente project with pgvector extension
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

### 1. Cannamente Database

This project requires the **cannamente** database to be running. Make sure:

1. The cannamente project is started and running
2. PostgreSQL is accessible on `localhost:5432`
3. Database credentials match the configuration

### 2. pgvector Extension

The database must have the pgvector extension installed. You can initialize it using:

```bash
# Initialize pgvector in external database
make init-pgvector
```

## Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd ai_budtender
```

### 2. Environment Setup

The `.env` file will be automatically created from `env.example` when you start the project. You can also create it manually:

```env
# External Database (cannamente project)
DATABASE_URL=postgresql://myuser:mypassword@host.docker.internal:5432/mydatabase
POSTGRES_DB=mydatabase
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_HOST=host.docker.internal
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

### 3. Initialize Database

```bash
# Initialize pgvector extension in external database
make init-pgvector
```

### 4. Start Project

```bash
# Using start script
./start.sh

# Or using Makefile
make start

# Or using Docker Compose directly
docker-compose up --build
```

### 5. Access Services

- **API**: http://localhost:8001 (changed to avoid conflict)
- **Documentation**: http://localhost:8001/api/v1/docs
- **PostgreSQL**: localhost:5432 (external cannamente DB)
- **Redis**: localhost:6380 (changed to avoid conflict)
- **Metrics**: http://localhost:9091 (changed to avoid conflict)

## Port Configuration

To avoid conflicts with the cannamente project, the following ports have been changed:

| Service | Original Port | New Port | Reason |
|---------|---------------|----------|---------|
| API | 8000 | 8001 | Avoid conflict with cannamente web |
| Metrics | 9090 | 9091 | Avoid potential conflicts |
| Redis | 6379 | 6380 | Avoid potential conflicts |

## Daily Usage Commands

### Starting the Project

```bash
# Start all services (recommended)
make start

# Start with logs
docker-compose up

# Start in background
docker-compose up -d
```

### Stopping the Project

```bash
# Stop all services
make stop

# Or
docker-compose down
```

### Checking Status

```bash
# Show service status
make status

# Show logs
make logs

# Check database connection
make check-db
```

### Development Commands

```bash
# Open shell in API container
make shell

# Open Redis CLI
make redis-cli

# Run tests
make test

# Restart services
make restart
```

### Maintenance Commands

```bash
# Clean up containers and volumes
make clean

# Build Docker images
make build

# Initialize pgvector in external database
make init-pgvector

# Create new database migration
make migration MSG="description"
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

# Build and start services
make build
make start

# Stop and restart
make stop
make restart

# Monitoring and logs
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
│   └── init_pgvector.py    # pgvector initialization
├── tests/                   # Tests
├── docker-compose.yml       # Docker configuration
├── Dockerfile              # Docker image
├── Makefile                # Development commands
├── alembic.ini             # Alembic configuration
└── requirements.txt        # Dependencies
```

## How It Works

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

## Troubleshooting

### Database Connection Issues

1. **Check if cannamente is running**:
   ```bash
   # In cannamente project directory
   docker-compose ps
   ```

2. **Verify database connection**:
   ```bash
   make check-db
   ```

3. **Initialize pgvector if needed**:
   ```bash
   make init-pgvector
   ```

4. **Check database logs**:
   ```bash
   # In cannamente directory
   docker-compose logs postgres
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

### pgvector Installation

If pgvector is not available in your PostgreSQL:

1. **For Ubuntu/Debian**:
   ```bash
   sudo apt-get install postgresql-15-pgvector
   ```

2. **For Docker**: Use `pgvector/pgvector:pg15` image in cannamente

3. **Manual installation**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

### Linux Docker Hostname Issues

If you're on Linux and get hostname resolution errors:

1. **Update docker-compose.yml** to use `host-gateway`:
   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```

2. **Or use host network**:
   ```yaml
   network_mode: host
   ```

## Integration with Cannamente

This project is designed to work alongside the **cannamente** project:

- **Shared Database**: Both projects use the same PostgreSQL instance
- **Separate Services**: Each project runs independently
- **Port Isolation**: Different ports to avoid conflicts
- **Data Sharing**: Products can be shared between projects

### Data Flow

1. **Cannamente** manages the main cannabis strain database
2. **AI Budtender** reads from the same database
3. **pgvector** enables semantic search across strain descriptions
4. **AI responses** are generated based on the shared data

## Migration from Standalone Mode

If you previously used this project with its own database:

1. **Backup your data** (if needed)
2. **Update configuration** to use external database
3. **Initialize pgvector** in the external database
4. **Restart services** with new configuration

## Performance Optimization

### For Production Use

1. **Increase Redis memory** for better caching
2. **Optimize database queries** with proper indexing
3. **Use connection pooling** for database connections
4. **Implement request queuing** for high load scenarios
5. **Add monitoring** with Prometheus and Grafana

### For Development

1. **Use mock mode** to avoid OpenAI API costs
2. **Enable hot reload** for faster development
3. **Use local development** mode with `make dev`
4. **Monitor logs** with `make logs`

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