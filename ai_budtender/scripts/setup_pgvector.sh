#!/bin/bash
# Script to automatically install pgvector in cannamente PostgreSQL container

set -e

echo "🔧 Setting up pgvector in cannamente database..."

# Check if cannamente database container is running
if ! docker ps | grep -q "canna-db-1"; then
    echo "❌ Cannamente database container (canna-db-1) is not running!"
    echo "Please start cannamente project first:"
    echo "cd ../cannamente && docker-compose up -d"
    exit 1
fi

echo "✅ Cannamente database container found"

# Install pgvector in the container
echo "📦 Installing pgvector extension..."
docker exec -it canna-db-1 bash -c "
    apt-get update && 
    apt-get install -y postgresql-13-pgvector &&
    echo 'pgvector installed successfully'
"

# Restart PostgreSQL to load the extension
echo "🔄 Restarting PostgreSQL to load pgvector..."
docker restart canna-db-1

# Wait for PostgreSQL to start
echo "⏳ Waiting for PostgreSQL to start..."
sleep 10

# Check if pgvector is working
echo "🔍 Checking pgvector installation..."
docker exec -it canna-db-1 psql -U myuser -d mydatabase -c "
    CREATE EXTENSION IF NOT EXISTS vector;
    SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
"

echo "✅ pgvector setup completed successfully!"
echo ""
echo "You can now run: make check-db" 