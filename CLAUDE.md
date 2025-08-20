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

  ---

  ## 🚧 **ТЕКУЩАЯ РАЗРАБОТКА: Context-Aware Architecture v2.0**

  **Статус:** Реализация архитектуры сохранения контекста из `follow-up-context-arc.md`

  **Проблема:** AI агент корректно отвечает на запросы подбора сортов, но теряет контекст обсуждения. При follow-up запросах система выполняет новый поиск вместо работы с уже рекомендованными сортами.

  **Цель:** Реализовать оптимизированную систему управления контекстом с минимальными вызовами LLM и robust fallback механизмами.

  ### ✅ **ШАГ 1 ЗАВЕРШЕН: Фундамент - Модели данных и Session Management**

  **Реализованные компоненты:**
  1. ✅ **Модель сессий** (`app/models/session.py`)
     - `ConversationSession` - основная модель сессии с восстановлением
     - `UnifiedAnalysis` - результат единого анализа LLM
     - JSON сериализация/десериализация с поддержкой Set и IntentType
     - Ограничения: макс 20 групп рекомендаций, макс 50 записей истории
     
  2. ✅ **Redis session manager** (`app/core/session_manager.py`)
     - `ImprovedSessionManager` - менеджер с graceful восстановлением
     - 4-часовой TTL для активных сессий, 7-дневный backup предпочтений
     - Восстановление истекших сессий с флагом `is_restored`
     - Статистика и мониторинг сессий
     
  3. ✅ **Обновленные API schemas** (`app/models/schemas.py`)
     - `ChatRequest` добавлены поля: `session_id`, `source_platform`
     - `ChatResponse` добавлены поля: `session_id`, `query_type`, `language`, `confidence`, `quick_actions`, `is_restored`, `is_fallback`, `warnings`
     
  4. ✅ **Redis integration** (`app/core/cache.py`)
     - Добавлена функция `get_redis()` для синхронного клиента
     - Поддержка существующего асинхронного кеша

  **Критерии тестирования ШАГ 1 (пройдены):**
  - ✅ Сессии создаются и сохраняются в Redis
  - ✅ JSON сериализация/десериализация работает корректно  
  - ✅ Session Manager управляет сессиями с восстановлением
  - ✅ Backup предпочтений функционирует
  - ✅ Модели UnifiedAnalysis готовы

  **Тестовые результаты:**
  ```bash
  # Тест создания сессии
  ✅ Сессия создана: e25c27ce-d0d1-4a3e-9763-10d1ba3d39d4
  
  # Тест сериализации
  ✅ JSON сериализация работает
  ✅ Восстановлены предпочтения: {'preferred_effects': {'Relaxed', 'Sleepy'}}
  
  # Тест Session Manager
  ✅ Сессия сохранена в Redis
  ✅ Статистика: {'active_sessions': 1, 'backup_sessions': 1}
  
  # Тест восстановления
  ✅ Сессия восстановлена с флагом is_restored=True
  ✅ Предпочтения восстановлены из backup
  ```

  ### ✅ **ШАГ 2 ЗАВЕРШЕН: Unified LLM Processor с Fallback**

  **Реализованные компоненты:**
  1. ✅ **UnifiedLLMProcessor** (`app/core/unified_processor.py`)
     - Единый промпт для полного анализа запроса (вместо 4-5 отдельных вызовов)
     - JSON extraction с fallback на парсинг обычного ответа
     - Context building из сессии для LLM
     - Валидация результатов с graceful fallback
     
  2. ✅ **RuleBasedFallbackAnalyzer** (`app/core/fallback_analyzer.py`)
     - Полностью автономная работа без OpenAI API
     - Детекция языка по ключевым словам (испанский/английский)
     - Query type detection (new_search, follow_up, reset, comparison)
     - Извлечение критериев по паттернам
     - Генерация quick actions на основе контекста
     
  3. ✅ **CriteriaConflictResolver** (`app/core/conflict_resolver.py`)
     - Детекция прямых конфликтов (хочу и избегаю одновременно)
     - Разрешение логических конфликтов (противоположные эффекты)
     - Медицинские предупреждения (высокий THC + anxiety)
     - Context-based приоритизация при конфликтах
     - Валидация общей консистентности критериев

  **Критерии тестирования ШАГ 2 (пройдены):**
  - ✅ Rule-based Fallback анализатор работает автономно
  - ✅ Детекция языка: испанский/английский по ключевым словам
  - ✅ Query types детектируются корректно (7/7 тест-кейсов)
  - ✅ Конфликты разрешаются с приоритизацией
  - ✅ Медицинские предупреждения генерируются
  - ✅ Context building для LLM функционирует
  - ✅ is_fallback флаг устанавливается правильно

  **Тестовые результаты:**
  ```bash
  # Fallback анализатор
  ✅ Испанский + новый поиск: new_search, эффекты: ['Sleepy']
  ✅ Английский + энергия: en, эффекты: ['Energetic']
  ✅ Follow-up запрос: follow_up, действие: filter
  ✅ Reset запрос: reset
  
  # Conflict resolver
  ✅ Прямой конфликт разрешен: "wanting and avoiding ['Sleepy']"
  ✅ Логический конфликт разрешен: приоритет Sleepy
  ✅ Медицинский конфликт: "High THC may worsen ['Anxiety']"
  
  # Unified LLM (с OpenAI доступным)
  ✅ LLM анализ работает: comparison, confidence: 0.85
  ✅ Context building: язык es, 4 strains, 3 preference categories
  ```

  ### ✅ **ШАГ 3 ЗАВЕРШЕН: Enhanced RAG Service с контекстом**

  **Реализованные компоненты:**
  1. ✅ **OptimizedContextualRAGService** (`app/core/optimized_rag_service.py`)
     - Главный метод `process_contextual_query` с интеграцией всех компонентов
     - Обработка 6 типов запросов: new_search, follow_up, comparison, reset, detail_request, clarification
     - Edge case handling: no_context, восстановленные сессии
     - Graceful degradation с fallback на правила при недоступности LLM
     
  2. ✅ **Repository enhancements** (`app/db/repository.py`)
     - `search_strains_with_filters()` - поиск с комбинированными фильтрами
     - `search_strains_by_name()` - поиск по имени сорта
     - Поддержка фильтрации по категориям, эффектам, потенциальности
     
  3. ✅ **Session context integration**
     - Обновление сессий с новыми предпочтениями и темами
     - Merge фильтров из анализа запроса и пользовательских предпочтений
     - Сохранение истории разговора и рекомендаций
     - Dynamic quick actions based на контекст

  **Критерии тестирования ШАГ 3 (пройдены):**
  - ✅ New search создает сессию и находит подходящие сорта
  - ✅ Follow-up запросы работают с существующими рекомендациями
  - ✅ Reset функциональность полностью очищает контекст
  - ✅ No context edge case обрабатывается с clarification
  - ✅ Conflict resolution интегрирован и работает
  - ✅ Session updates корректно обновляют язык, тему, предпочтения

  **Тестовые результаты:**
  ```bash
  # New search
  ✅ Новый поиск: new_search, язык: es, найдено: 2 сорта
  
  # Follow-up context
  ✅ Follow-up запрос: follow_up, использует сессию
  ✅ Обработано существующих сортов: 3
  
  # Reset functionality  
  ✅ Reset выполнен, контекст очищен: история = 0
  ✅ Quick actions: ['Para dormir', 'Para energía', 'Para dolor']
  
  # Edge cases
  ✅ No context обработан: clarification с предложениями
  ✅ Конфликты детектированы: 2 ("Direct conflict: wanting and avoiding")
  
  # Session management
  ✅ Язык обновлен: en, тема: creativity
  ✅ Предпочтения обновлены, история: 1 записей
  ```

  ### 🎉 **CONTEXT-AWARE ARCHITECTURE v2.0 - ЗАВЕРШЕНА И РАБОТАЕТ!**

  **Статус:** ✅ ПОЛНОСТЬЮ РЕАЛИЗОВАНА И ПРОТЕСТИРОВАНА

  **Финальные компоненты (ЗАВЕРШЕННЫЕ):**

  1. ✅ **AdaptiveStrainSearch** (`app/core/adaptive_search.py`) - КРИТИЧЕСКОЕ РЕШЕНИЕ
     - 5-этапная адаптивная система поиска с постепенным ослаблением фильтров
     - Решает проблему "слишком строгие фильтры = 0 результатов"
     - Этапы: строгие → ослабленные → только категории → семантический → fallback
     
  2. ✅ **OptimizedContextualRAGService** (`app/core/optimized_rag_service.py`) - ГЛАВНЫЙ СЕРВИС
     - Полная интеграция всех компонентов Context-Aware архитектуры
     - Поддержка 6 типов запросов: new_search, follow_up, comparison, reset, detail_request, clarification
     - Unified LLM с fallback системой
     - Session management с восстановлением
     - Conflict resolution для противоречивых критериев
     
  3. ✅ **API Integration** (`app/api/chat.py`) - BACKWARD COMPATIBLE
     - Флаг `USE_CONTEXTUAL_RAG=true` активирует новую архитектуру
     - Полная совместимость с существующим API
     - Все поля ChatResponse поддерживаются
     
  4. ✅ **Docker & Environment** - PRODUCTION READY
     - Все переменные окружения добавлены в docker-compose.yml и env.example
     - Session TTL, backup, cache настройки
     - Контейнеры перезапущены с новыми переменными

  **ИНТЕГРАЦИОННОЕ ТЕСТИРОВАНИЕ - ВСЕ ТЕСТЫ ПРОХОДЯТ:**

  ```bash
  🎉 ВСЕ ИНТЕГРАЦИОННЫЕ ТЕСТЫ ЗАВЕРШЕНЫ!
  ✅ Проверенная функциональность:
    • Multi-step диалоги с сохранением контекста  
    • Follow-up запросы работают с session_id
    • Переключение языков в рамках одной сессии
    • Reset функциональность
    • Conflict resolution и предупреждения
    • Query type detection в реальных условиях
    • Session management через Redis
  🔄 Context-Aware Architecture v2.0 работает корректно!
  ```

  **ПРИМЕРЫ РЕАЛЬНЫХ ДИАЛОГОВ (РАБОЧИЕ):**

  1. **Испанский диалог про сон:**
     - "Necesito algo para dormir bien por las noches" → 2 Indica сорта
     - "¿Cuál de estos es más fuerte?" → follow_up работает с session_id
     - "¿Hay algo más suave?" → адаптивный поиск находит альтернативы

  2. **Английский диалог с reset:**
     - "I need something energizing for work and focus" → Sativa/Hybrid сорта
     - "Which one is best for creativity?" → comparison из контекста
     - "Actually, start over - I need something for pain relief" → reset + новый поиск

  3. **Смешанный диалог (ES→EN→ES):**
     - "Quiero algo para la creatividad" → поиск на испанском
     - "Which of these has the least side effects?" → переключение на английский
     - "¿Y para principiantes?" → обратно на испанский

  **РЕШЕННЫЕ ПРОБЛЕМЫ:**
  
  ✅ **Основная проблема**: AI агент терял контекст - РЕШЕНА
  ✅ **Search filters слишком строгие**: AdaptiveSearch - РЕШЕНА  
  ✅ **Множественные LLM вызовы**: Unified processor - РЕШЕНА
  ✅ **Нет fallback системы**: Rule-based analyzer - РЕШЕНА
  ✅ **Конфликты в критериях**: Conflict resolver - РЕШЕНА
  ✅ **Session management**: Redis с backup - РЕШЕНА

  **PRODUCTION STATUS:** 
  🚀 Context-Aware Architecture v2.0 готова к использованию в cannamente UI
  
  **Активация:** `USE_CONTEXTUAL_RAG=true` (уже установлено)
