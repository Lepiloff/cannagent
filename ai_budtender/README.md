# AI Budtender - Smart Cannabis Product Selection Assistant

## Description

AI Budtender is a local prototype of a cloud service that provides an intelligent chatbot for cannabis product e-commerce websites. The bot helps users with product selection, answers questions about products and makes recommendations based on vector search (RAG).

## Technologies

- **Backend**: Python 3.11+, FastAPI
- **Database**: PostgreSQL 15+ with pgvector extension
- **AI/ML**: LangChain, OpenAI API (with mock mode support)
- **Vector Search**: pgvector for semantic search
- **Containerization**: Docker, Docker Compose
- **Testing**: Pytest, FastAPI TestClient
- **Caching**: Redis for embeddings and responses
- **Monitoring**: Prometheus metrics
- **Rate Limiting**: SlowAPI for request throttling
- **Logging**: Structured logging with JSON format
- **Migrations**: Alembic for database versioning

## Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd ai_budtender
```

### 2. Environment Setup

The `.env` file will be automatically created from `env.example` when you start the project. You can also create it manually:

```env
# Database
DATABASE_URL=postgresql://user:password@db:5432/ai_budtender
POSTGRES_DB=ai_budtender
POSTGRES_USER=user
POSTGRES_PASSWORD=password

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

### 3. Start Project

```bash
# Using start script
./start.sh

# Or using Makefile
make start

# Or using Docker Compose directly
docker-compose up --build
```

### 4. Access Services

- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/api/v1/docs
- **Adminer (Database)**: http://localhost:8080
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Metrics**: http://localhost:8000/metrics

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
│   └── init_db.py          # Database initialization
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

# View logs
make logs

# Run tests
make test

# Create database migration
make migration MSG="Add new field"

# Initialize database
make init-db

# Open API container shell
make shell

# Open Redis CLI
make redis-cli

# Clean up containers and volumes
make clean
```

## Data Management

### Import Products from CSV

```python
from app.utils.data_import import import_products_from_csv
count = import_products_from_csv("products.csv")
```

### Import Products from JSON

```python
from app.utils.data_import import import_products_from_json
count = import_products_from_json("products.json")
```

### Initialize Sample Data

Sample products are automatically created on first startup.

## Testing

```bash
# Run tests
make test

# Run tests with coverage
docker-compose exec api pytest --cov=app

# Run specific test file
docker-compose exec api pytest tests/test_main.py -v
```

## Operating Modes

### Mock Mode (Default)
- No OpenAI API key required
- Uses dummy embeddings and responses
- Suitable for testing and demonstration

### Production Mode
- Requires OPENAI_API_KEY
- Uses real OpenAI embeddings
- Generates high-quality responses

## Features

### ✅ Implemented Improvements

- **Redis Caching**: Embeddings and responses cached for performance
- **Rate Limiting**: Request throttling to prevent abuse
- **Structured Logging**: JSON formatted logs for better analysis
- **Prometheus Metrics**: Comprehensive monitoring and alerting
- **Async Operations**: Improved performance with async database operations
- **Alembic Migrations**: Database versioning and schema management
- **Health Checks**: Comprehensive service health monitoring

### 🔧 Performance Optimizations

- **Connection Pooling**: Efficient database connection management
- **Vector Indexing**: Optimized pgvector operations
- **Request Batching**: Efficient bulk operations
- **Memory Management**: Optimized embedding storage

## Debugging

### Service Logs
```bash
# All logs
make logs

# API logs
docker-compose logs api

# Database logs
docker-compose logs db

# Redis logs
docker-compose logs redis
```

### Database Connection
```bash
# Via Adminer: http://localhost:8080
# System: PostgreSQL
# Server: db
# Username: user
# Password: password
# Database: ai_budtender
```

### Redis Connection
```bash
# Via Redis CLI
make redis-cli

# Or direct connection
redis-cli -h localhost -p 6379
```

## Project Management

```bash
# Stop services
make stop

# Stop with data removal
make clean

# Backup database
make backup

# Restore database
make restore
```

## Future Enhancements

- ✅ **Redis Caching** - Implemented
- ✅ **Rate Limiting** - Implemented  
- ✅ **Structured Logging** - Implemented
- ✅ **Prometheus Metrics** - Implemented
- ✅ **Async Operations** - Implemented
- ✅ **Alembic Migrations** - Implemented
- 🔄 **JWT Authentication** - Planned
- 🔄 **WebSocket Support** - Planned
- 🔄 **Multi-language Support** - Planned
- 🔄 **Advanced Analytics** - Planned
- 🔄 **AWS Migration** - Planned

## License

MIT License 