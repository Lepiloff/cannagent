# AI Budtender - Integration Guide with Cannamente

## Overview

AI Budtender has been configured to work with the existing **cannamente** database. This guide explains how to set up and run the integrated system.

## Prerequisites

1. **Cannamente Project Running**: Make sure the cannamente project is started and running
2. **Database Access**: PostgreSQL should be accessible on `localhost:5432`
3. **pgvector Extension**: The database needs the pgvector extension for vector search

## Configuration Changes Made

### 1. Database Integration
- **External Database**: AI Budtender now connects to cannamente's PostgreSQL database
- **Shared Data**: Uses existing `strains` table from cannamente
- **Vector Search**: Adds embedding column to strains table for semantic search

### 2. Port Configuration
To avoid conflicts with cannamente, ports have been changed:

| Service | Original Port | New Port | Reason |
|---------|---------------|----------|---------|
| API | 8000 | 8001 | Avoid conflict with cannamente web |
| Metrics | 9090 | 9091 | Avoid potential conflicts |
| Redis | 6379 | 6380 | Avoid potential conflicts |

### 3. Data Model Integration
- **Strain Model**: Added SQLAlchemy model matching cannamente's Strain structure
- **Backward Compatibility**: Kept legacy Product model for compatibility
- **Rich Data**: Leverages existing strain data (THC, CBD, category, effects, etc.)

## Setup Instructions

### Step 1: Verify Cannamente Database
```bash
# Check if cannamente is running
docker ps | grep canna

# Verify database connection
make check-db
```

### Step 2: Initialize pgvector
```bash
# Initialize pgvector extension in cannamente database
make init-pgvector
```

### Step 3: Start AI Budtender
```bash
# Start the service
make start

# Or using Docker Compose directly
docker-compose up -d
```

### Step 4: Verify Integration
```bash
# Check service status
make status

# Test API endpoints
curl http://localhost:8001/api/v1/ping/
curl http://localhost:8001/api/v1/products/
```

## API Endpoints

### Health Check
```bash
GET http://localhost:8001/api/v1/ping/
```

### Get Strains (from cannamente)
```bash
GET http://localhost:8001/api/v1/strains/
```

### Chat with AI Budtender
```bash
POST http://localhost:8001/api/v1/chat/ask/
Content-Type: application/json

{
  "message": "Recommend something for evening relaxation",
  "history": []
}
```

## Data Flow

1. **User Query**: User sends question to AI Budtender
2. **Embedding Generation**: Query is converted to vector embedding
3. **Vector Search**: Similar strains are found using pgvector
4. **Context Formation**: Strain data (THC, CBD, effects, etc.) is prepared
5. **AI Response**: LLM generates personalized recommendation
6. **Result**: Response with recommended strains returned

## Database Schema

### Strains Table (from cannamente)
```sql
CREATE TABLE strains (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    title VARCHAR(255),
    text_content TEXT,
    description VARCHAR(255),
    keywords VARCHAR(255),
    cbd DECIMAL(5,2),
    thc DECIMAL(5,2),
    cbg DECIMAL(5,2),
    rating DECIMAL(3,1),
    category VARCHAR(10),
    img VARCHAR(255),
    img_alt_text VARCHAR(255),
    active BOOLEAN DEFAULT FALSE,
    top BOOLEAN DEFAULT FALSE,
    main BOOLEAN DEFAULT FALSE,
    is_review BOOLEAN DEFAULT FALSE,
    slug VARCHAR(255) UNIQUE,
    embedding vector(1536),  -- Added by AI Budtender
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Vector Search Index
```sql
CREATE INDEX strains_embedding_idx 
ON strains 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

## Troubleshooting

### Database Connection Issues
```bash
# Check cannamente status
docker ps | grep canna

# Verify database connection
make check-db

# Check database logs
docker logs canna-db-1
```

### Port Conflicts
```bash
# Check what's using the ports
sudo netstat -tlnp | grep :8001
sudo netstat -tlnp | grep :9091
sudo netstat -tlnp | grep :6380
```

### pgvector Issues
```bash
# Reinitialize pgvector
make init-pgvector

# Check pgvector installation
docker exec canna-db-1 psql -U myuser -d mydatabase -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

## Development Commands

```bash
# Start services
make start

# Stop services
make stop

# View logs
make logs

# Check database connection
make check-db

# Initialize pgvector
make init-pgvector

# Run tests
make test

# Open shell in container
make shell

# Show service status
make status
```

## Integration Benefits

1. **Shared Data**: No need to duplicate strain information
2. **Rich Context**: Access to detailed strain data (THC, CBD, effects, etc.)
3. **Consistent Updates**: Changes in cannamente automatically available to AI Budtender
4. **Scalable Architecture**: Separate services, shared database
5. **Vector Search**: Semantic search across existing strain database

## Next Steps

1. **Test Integration**: Verify that AI Budtender can access and search strains
2. **Generate Embeddings**: Create embeddings for existing strains
3. **Test Chat Functionality**: Verify AI recommendations work with real strain data
4. **Monitor Performance**: Check metrics and logs for optimization opportunities 