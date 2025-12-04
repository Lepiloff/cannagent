FROM postgres:15

# Install pgvector extension
RUN apt-get update && \
    apt-get install -y postgresql-15-pgvector && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create extensions on database initialization
RUN echo "CREATE EXTENSION IF NOT EXISTS vector;" > /docker-entrypoint-initdb.d/01-init-pgvector.sql && \
    echo "CREATE EXTENSION IF NOT EXISTS pg_trgm;" > /docker-entrypoint-initdb.d/02-init-pgtrgm.sql
