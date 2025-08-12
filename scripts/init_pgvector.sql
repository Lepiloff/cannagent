-- Minimal pgvector initialization for production deployment
-- This script only enables the pgvector extension for AI Budtender
-- All other database schema is managed by SQLAlchemy through create_tables()

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Optionally set some performance optimizations for production
-- These can be adjusted based on your hardware and data size
-- SET max_connections = 200;
-- SET shared_buffers = '256MB';
-- SET effective_cache_size = '1GB';
-- SET random_page_cost = 1.1;

-- Note: Schema, tables, and relationships are automatically created by:
-- 1. SQLAlchemy models in app/models/database.py 
-- 2. create_tables() function in app/db/database.py
-- 3. Data and embeddings populated by scripts/sync_strain_relations.py