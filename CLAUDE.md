Project Structure Analysis: AI Budtender 🌿

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

  - chat.py - Main chat/recommendation endpoint with intent detection
  - strains.py - Strain management and browsing
  - health.py - Health checks and monitoring

  Data Layer (app/db/, app/models/)

  - database.py - SQLAlchemy setup
  - repository.py - Data access patterns
  - schemas.py - Pydantic models

  Automation (scripts/)

  - init_database.py - Full database initialization for production deployment
  - sync_daily.py - Daily incremental synchronization for production  
  - sync_strain_relations.py - Full sync with structured data (working script)
  - common.py - Shared functions for sync scripts
  - init_pgvector.sql - pgvector extension setup

  Key Features

  ✅ Vector similarity search for product recommendations✅ RAG-powered conversational AI✅ Rate limiting (100 req/min default)✅ Redis caching with TTL✅ Prometheus metrics collection✅ Health checks and
  monitoring✅ Mock mode for development without OpenAI✅ Automated data synchronization

  Database Connections

  **Local AI Budtender Database (Inside Docker)**
  ```python
  # From within container
  DATABASE_URL = "postgresql://user:password@db:5432/ai_budtender"
  
  # Direct psycopg2 connection from container
  psycopg2.connect(
      host='db',
      port=5432,
      database='ai_budtender', 
      user='user',
      password='password'
  )
  ```

  **External Cannamente Database (From host/container)**
  ```python
  # Connection configs to try in order:
  configs = [
      {
          'host': 'localhost',  # From host machine
          'port': 5432,
          'database': 'mydatabase',
          'user': 'myuser', 
          'password': 'mypassword'
      },
      {
          'host': 'host.docker.internal',  # From container to host
          'port': 5432,
          'database': 'mydatabase',
          'user': 'myuser',
          'password': 'mypassword' 
      }
  ]
  ```

  **Testing Connections & Commands**
  ```bash
  # Test API inside container
  docker compose exec api python -c "
  import requests
  response = requests.get('http://localhost:8001/')
  print('Status:', response.status_code)
  print('Response:', response.json())
  "
  
  # Test sleep query  
  docker compose exec api python -c "
  import requests
  response = requests.post(
      'http://localhost:8001/api/v1/chat/ask',
      json={'message': 'Recomiéndame una variedad para dormir bien'}
  )
  result = response.json()
  print(f'Found {len(result[\"recommended_strains\"])} strains')
  "
  
  # Check strains count
  docker compose exec api python -c "
  from app.db.database import SessionLocal
  from app.db.repository import StrainRepository
  db = SessionLocal()
  repo = StrainRepository(db)
  strains = repo.get_strains(limit=10)
  print(f'Total strains: {len(strains)}')
  for strain in strains:
      print(f'  - {strain.name} ({strain.category})')
  db.close()
  "
  
  # Run sync from cannamente (if available)
  docker compose exec api python scripts/sync_strain_relations.py
  ```

  **Recent Fixes & Optimizations (Latest Session)**
  - Fixed critical PostgreSQL DISTINCT/ORDER BY conflict in vector similarity queries
  - Expanded sleep filter to include both Indica and Hybrid strains for better variety (now returns 2+ strains)
  - Expanded energy filter to include Hybrid strains (not just Sativa) for more comprehensive recommendations
  - Improved intent detection system to return multiple appropriate options instead of single results
  - SQL queries restructured using subquery approach to avoid database conflicts
  - **API Response Optimization**: Removed 8-10 unnecessary fields per strain (rating, img, timestamps, internal flags)
  - **Enhanced Vector Embeddings**: Now include CBG content and negative effects for better search accuracy
  - **CompactStrain Schema**: New optimized response format for cannamente UI integration
  - **Production Ready**: Successfully tested all README.md commands and API endpoints

  **Current API Response Format (CompactStrain)**
  ```json
  {
    "response": "I recommend Northern Lights for relaxation and sleep...",
    "recommended_strains": [
      {
        "id": 42,
        "name": "Northern Lights",
        "cbd": "0.10", "thc": "18.50", "cbg": "1.00",
        "category": "Indica",
        "slug": "northern-lights",
        "url": "http://localhost:8001/strain/northern-lights/",
        "feelings": [
          {"name": "Sleepy"},
          {"name": "Relaxed"},
          {"name": "Hungry"}
        ],
        "helps_with": [
          {"name": "Insomnia"},
          {"name": "Stress"}, 
          {"name": "Pain"}
        ],
        "negatives": [
          {"name": "Dry mouth"},
          {"name": "Dry eyes"},
          {"name": "Dizzy"}
        ],
        "flavors": [
          {"name": "earthy"},
          {"name": "pine"},
          {"name": "sweet"}
        ]
      }
    ],
    "detected_intent": "sleep",
    "filters_applied": {
      "preferred_categories": ["Indica"],
      "exclude_feelings": ["Energetic", "Talkative"]
    }
  }
  ```

  **Intent Detection System**
  - IntentType.SLEEP: Prefers Indica & Hybrid, requires Sleepy/Relaxed/Hungry, excludes Energetic/Talkative
  - IntentType.ENERGY: Prefers Sativa & Hybrid, requires Energetic/Uplifted, excludes Sleepy/Relaxed  
  - IntentType.CREATIVITY: Prefers Sativa & Hybrid, requires Creative/Euphoric, excludes Sleepy
  - IntentType.FOCUS: Prefers Sativa & Hybrid, requires Focused/Creative, excludes Sleepy/Giggly
  - All filters now include appropriate Hybrid strains for better variety

  **Vector Embedding Enhancement**
  - Includes strain name, description, category, and cannabinoid content (THC, CBD, CBG)
  - Incorporates structured effects data (feelings, helps_with, negatives, flavors)
  - CBG content and negative effects are now part of vector generation for better filtering
  - Text format: "Northern Lights Classic indica THC: 18.5% CBD: 0.1% CBG: 1.0% Effects: Sleepy, Relaxed Side effects: Dry mouth"

  **Current Production Status (MVP Complete)**
  - ✅ All README.md commands tested and working
  - ✅ API endpoints validated on port 8001
  - ✅ Database synchronized with 173 strains from cannamente
  - ✅ Vector embeddings regenerated with CBG + negatives
  - ✅ CompactStrain schema deployed for optimized API responses
  - ✅ Intent detection system functioning with multiple strain results
  - ✅ Makefile commands updated and functional
  - ✅ Documentation updated for cannamente developers

  Deployment

  - Development: make start (Docker Compose)
  - Ports: API (8001), Metrics (9091), Redis (6380), Local DB (5433)
  - External Dependencies: cannamente database (port 5432)
  - Production Scripts: init_database.py, sync_daily.py, sync_strain_relations.py
