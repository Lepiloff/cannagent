# AI Budtender Integration Guide

## Overview

This guide explains how to integrate AI Budtender with the existing cannamente project, including database setup, configuration changes, and troubleshooting.

## Prerequisites

1. **Cannamente project** must be running
2. **PostgreSQL** with pgvector extension
3. **Docker and Docker Compose** installed

## Database Setup

### Option 1: Permanent pgvector Installation (Recommended)

To avoid reinstalling pgvector after each restart, create a custom PostgreSQL image:

1. **Create custom Dockerfile in cannamente project:**

```dockerfile
# cannamente/docker/postgres-pgvector.Dockerfile
FROM postgres:13

# Install pgvector extension
RUN apt-get update && \
    apt-get install -y postgresql-13-pgvector && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create extension on database initialization
RUN echo "CREATE EXTENSION IF NOT EXISTS vector;" > /docker-entrypoint-initdb.d/01-init-pgvector.sql
```

2. **Update cannamente docker-compose.yml:**

```yaml
services:
  db:
    build:
      context: .
      dockerfile: docker/postgres-pgvector.Dockerfile
    # ... rest of configuration
```

3. **Rebuild and restart cannamente:**

```bash
cd cannamente
docker-compose down
docker-compose build db
docker-compose up -d
```

### Option 2: Manual Installation (Temporary)

If you prefer manual installation, use the provided script:

```bash
# In ai_budtender directory
./scripts/setup_pgvector.sh
```

**Note:** This needs to be repeated after each container restart.

## Configuration Changes

### Port Configuration

To avoid conflicts, AI Budtender uses different ports:

| Service | AI Budtender Port | Cannamente Port |
|---------|-------------------|-----------------|
| Web API | 8001 | 8000 |
| Metrics | 9091 | 9090 |
| Redis | 6380 | 6379 |

### Database Connection

AI Budtender connects to cannamente's PostgreSQL using:

```env
DATABASE_URL=postgresql://myuser:mypassword@host-gateway:5432/mydatabase
POSTGRES_HOST=host-gateway
```

## Setup Steps

### 1. Start Cannamente

```bash
cd cannamente
docker-compose up -d
```

### 2. Initialize pgvector

```bash
# Option 1: If using custom image (permanent)
# No action needed - extension is auto-installed

# Option 2: Manual installation
cd ai_budtender
./scripts/setup_pgvector.sh
```

### 3. Start AI Budtender

```bash
cd ai_budtender
make start
```

### 4. Verify Integration

```bash
# Check database connection
make check-db

# Check service status
make status

# Test API
curl http://localhost:8001/api/v1/ping/
```

## API Endpoints

### Health Check
```bash
GET http://localhost:8001/api/v1/ping/
```

### Chat with AI
```bash
POST http://localhost:8001/api/v1/chat/ask/
Content-Type: application/json

{
  "message": "Recommend something for evening relaxation",
  "history": []
}
```

### Get Products
```bash
GET http://localhost:8001/api/v1/products/
```

## Data Flow

1. **Cannamente** manages cannabis strain data in PostgreSQL
2. **AI Budtender** reads from the same database
3. **pgvector** enables semantic search across strain descriptions
4. **AI responses** are generated based on the shared data

## Database Schema

AI Budtender works with the existing `strains_strain` table from cannamente:

```sql
-- Existing cannamente table
CREATE TABLE strains_strain (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    text_content TEXT,
    cbd DECIMAL(5,2),
    thc DECIMAL(5,2),
    cbg DECIMAL(5,2),
    rating DECIMAL(3,2),
    category VARCHAR(100),
    img VARCHAR(255),
    img_alt_text VARCHAR(255),
    active BOOLEAN DEFAULT true,
    top BOOLEAN DEFAULT false,
    main BOOLEAN DEFAULT false,
    is_review BOOLEAN DEFAULT false,
    slug VARCHAR(255),
    embedding vector(1536)  -- Added by AI Budtender
);
```

## Troubleshooting

### Database Connection Issues

1. **Check if cannamente is running:**
   ```bash
   docker ps | grep canna
   ```

2. **Verify database connection:**
   ```bash
   make check-db
   ```

3. **Check pgvector installation:**
   ```bash
   docker exec -it canna-db-1 psql -U myuser -d mydatabase -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
   ```

### Port Conflicts

If you encounter port conflicts:

1. Check if cannamente is using the same ports
2. Modify ports in `docker-compose.yml` if needed
3. Restart services: `make restart`

### pgvector Not Working

If pgvector is not available:

1. **For custom image approach:**
   ```bash
   cd cannamente
   docker-compose build db
   docker-compose up -d
   ```

2. **For manual installation:**
   ```bash
   ./scripts/setup_pgvector.sh
   ```

## Benefits of Integration

1. **Shared Data**: Both projects use the same cannabis strain database
2. **No Duplication**: Avoid maintaining separate databases
3. **Consistent Data**: Changes in cannamente are immediately available to AI Budtender
4. **Resource Efficiency**: Single PostgreSQL instance for both projects

## Vector Data Persistence

**Important**: Vector embeddings are stored in the database and persist across restarts:

- ✅ **Vector data** → stored in PostgreSQL volume (persists)
- ✅ **Strain data** → stored in PostgreSQL volume (persists)  
- ❌ **pgvector extension** → installed in container filesystem (lost on rebuild)

This is why the custom PostgreSQL image approach is recommended for production use. 