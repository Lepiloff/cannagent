# Quick Start Guide

## After System Restart

If you've restarted your system and need to get AI Budtender running again:

### 1. Start Cannamente (if not running)
```bash
cd ../cannamente
docker-compose up -d
```

### 2. Setup pgvector (one-time after restart)
```bash
cd ai_budtender
make setup-pgvector
```

### 3. Start AI Budtender
```bash
make start
```

### 4. Verify everything works
```bash
make check-db
make status
curl http://localhost:8001/api/v1/ping/
```

## Why pgvector needs to be reinstalled?

- **Database data** → persists in Docker volumes ✅
- **Vector embeddings** → persist in database ✅  
- **pgvector extension** → installed in container filesystem ❌

The pgvector extension is installed in the PostgreSQL container's filesystem, not in the data volume. When the container is recreated (after restart), the extension is lost but the data remains.

## Permanent Solution

For production use, consider creating a custom PostgreSQL image with pgvector pre-installed:

1. Create `cannamente/docker/postgres-pgvector.Dockerfile`
2. Update `cannamente/docker-compose.yml` to use custom image
3. Rebuild cannamente database

This way pgvector will be automatically available after any restart.

## Daily Commands

```bash
# Start services
make start

# Stop services  
make stop

# Check status
make status

# View logs
make logs

# Check database
make check-db
``` 