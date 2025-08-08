roject Structure Analysis: AI Budtender 🌿

  This is a Cannabis Strain Recommendation System built with Python FastAPI, implementing RAG (Retrieval-Augmented Generation) and vector search capabilities.

  Architecture Overview

  AI Budtender (FastAPI + RAG)
  ├── External DB (cannamente) → Local DB (pgvector) → Client API
  ├── Vector Search + AI Processing + Redis Caching
  └── Metrics + Rate Limiting + Health Checks

  Tech Stack

  - Backend: FastAPI, Python 3.x
  - Database: PostgreSQL with pgvector extension
  - AI/ML: LangChain, OpenAI API, vector embeddings
  - Caching: Redis
  - Containerization: Docker + Docker Compose
  - Monitoring: Prometheus metrics, structured logging (structlog)
  - Security: Rate limiting (slowapi), CORS middleware

  Key Components

  Core Services (app/core/)

  - rag_service.py - RAG implementation with vector search
  - llm_interface.py - OpenAI API integration
  - cache.py, rate_limiter.py, metrics.py - Infrastructure
  - logging.py - Structured logging setup

  API Layer (app/api/)

  - chat.py - Main chat/recommendation endpoint
  - products.py - Product management
  - health.py - Health checks

  Data Layer (app/db/, app/models/)

  - database.py - SQLAlchemy setup
  - repository.py - Data access patterns
  - schemas.py - Pydantic models

  Automation (scripts/)

  - Data sync from external "cannamente" database
  - Health monitoring and initialization scripts

  Key Features

  ✅ Vector similarity search for product recommendations✅ RAG-powered conversational AI✅ Rate limiting (100 req/min default)✅ Redis caching with TTL✅ Prometheus metrics collection✅ Health checks and
  monitoring✅ Mock mode for development without OpenAI✅ Automated data synchronization

  Deployment

  - Development: make start (Docker Compose)
  - Ports: API (8001), Metrics (9091), Redis (6380), Local DB (5433)
  - External Dependencies: cannamente database (port 5432)
