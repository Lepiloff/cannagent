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

## API Usage

### Main Endpoints

#### 1. Health Check
```bash
GET /api/v1/ping/
```

#### 2. Get Products
```bash
GET /api/v1/products/
```

#### 3. Create Product
```bash
POST /api/v1/products/
Content-Type: application/json

{
  "name": "Blue Dream",
  "description": "Sativa-Indica hybrid for daytime use"
}
```

#### 4. Chat with AI Budtender
```bash
POST /api/v1/chat/ask/
Content-Type: application/json

{
  "message": "Recommend something for evening relaxation",
  "history": []
}
```

#### 5. Cache Management
```bash
# Get cache statistics
GET /api/v1/cache/stats/

# Clear cache
POST /api/v1/cache/clear/
```

#### 6. Metrics
```bash
GET /metrics
```

### Chat Response Example

```json
{
  "response": "For evening relaxation I recommend...",
  "recommended_products": [
    {
      "id": 1,
      "name": "Northern Lights",
      "description": "Classic indica for relaxation",
      "created_at": "2024-01-01T12:00:00Z"
    }
  ]
}
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

## Algorithm Flow

1. **Request Reception**: User sends question through API
2. **Embedding Generation**: Creates vector representation of query  
3. **Vector Search**: Searches for similar products via pgvector
4. **Context Formation**: Prepares data for LLM
5. **Response Generation**: LLM creates personalized answer
6. **Result Return**: Response and recommendations sent to user

## Development Commands

```bash
# Start all services
make start

# Stop all services  
make stop

# Show logs
make logs

# Initialize pgvector in external database
make init-pgvector

# Check database connection
make check-db

# Show service status
make status

# Run tests
make test

# Open shell in API container
make shell

# Clean up
make clean
```

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

### Port Conflicts

If you encounter port conflicts:

1. Check if cannamente is using the same ports
2. Modify ports in `docker-compose.yml` if needed
3. Restart services: `make restart`

### pgvector Installation

If pgvector is not available in your PostgreSQL:

1. **For Ubuntu/Debian**:
   ```bash
   sudo apt-get install postgresql-15-pgvector
   ```

2. **For Docker**: Use `pgvector/pgvector:pg15` image in cannamente

## Integration with Cannamente

This project is designed to work alongside the **cannamente** project:

- **Shared Database**: Both projects use the same PostgreSQL instance
- **Separate Services**: Each project runs independently
- **Port Isolation**: Different ports to avoid conflicts
- **Data Sharing**: Products can be shared between projects

## Migration from Standalone Mode

If you previously used this project with its own database:

1. **Backup your data** (if needed)
2. **Update configuration** to use external database
3. **Initialize pgvector** in the external database
4. **Restart services** with new configuration 