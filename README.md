# AI Budtender - Cannabis Strain Recommendation System

Интеллектуальная система рекомендаций каннабиса с использованием RAG (Retrieval-Augmented Generation) и векторного поиска.

## 🚀 Быстрый старт

### Ежедневный флоу

```bash
# Утром (после перезагрузки):
cd ../cannamente && docker-compose up -d
cd ai_budtender && make start

# В течение дня:
make sync-cannamente  # синхронизировать данные
make check-db         # проверить подключение
make logs            # посмотреть логи

# Вечером:
make stop
cd ../cannamente && docker-compose down
```

### Первоначальная настройка

1. **Создать .env файл:**
```bash
cp env.example .env
# Отредактировать при необходимости
```

2. **Запустить систему:**
```bash
make start
```

3. **Синхронизировать данные:**
```bash
make sync-cannamente
```

## 🛠 Команды

### Основные команды
```bash
make start           # Запустить все сервисы
make stop            # Остановить сервисы
make restart         # Перезапустить
make logs            # Логи в реальном времени
```

### Мониторинг
```bash
make check-db        # Проверка подключения к БД
make status          # Статус сервисов
make shell           # Shell в контейнере
make redis-cli       # Redis CLI
```

### Синхронизация данных
```bash
make sync-cannamente    # Синхронизировать все данные
make sync-new           # Синхронизировать только новые
make watch-cannamente   # Автоматический мониторинг
```

### Разработка
```bash
make test            # Запустить тесты
make build          # Собрать образы
make clean          # Очистить контейнеры и volumes
```

## 🏗 Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Cannamente    │    │   AI Budtender   │    │     Client      │
│   (Client DB)   │───▶│   (Local DB)     │───▶│   (Frontend)    │
│                 │    │                  │    │                 │
│ - strains data  │    │ - Vector search  │    │ - Chat UI       │
│ - READ ONLY     │    │ - AI processing  │    │ - API calls     │
│ - GET/SELECT    │    │ - Cached data    │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Преимущества:**
- ✅ Локальная БД с pgvector (данные сохраняются)
- ✅ Быстрый векторный поиск
- ✅ Независимость от внешних сервисов
- ✅ Автоматическая проверка здоровья при запуске

## 🌐 API Endpoints

### Health Check
```bash
curl http://localhost:8001/api/v1/ping/
```

### Chat
```bash
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Recommend something for relaxation", "history": []}'
```

### Products
```bash
curl http://localhost:8001/api/v1/products/
```

### Cache Management
```bash
curl http://localhost:8001/api/v1/cache/stats/    # Статистика
curl -X POST http://localhost:8001/api/v1/cache/clear/  # Очистить
```

### Metrics
```bash
curl http://localhost:8001/metrics
```

## ⚙️ Конфигурация

### Порты
- **API**: 8001
- **Metrics**: 9091  
- **Redis**: 6380
- **Local DB**: 5433
- **External DB**: 5432 (cannamente)

### Environment Variables

Основные настройки в `.env`:

```env
# OpenAI API
OPENAI_API_KEY=your_key_here
MOCK_MODE=true

# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=ai_budtender
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## 🔧 Устранение проблем

### БД не подключается
```bash
# Проверить cannamente
docker ps | grep canna

# Проверить подключения
make check-db

# Перезапустить
make restart
```

### Нет данных
```bash
# Синхронизировать из cannamente
make sync-cannamente
```

### Сервисы не запускаются
```bash
# Очистить и пересоздать
make clean
make start
```

## 🧪 Тестирование

```bash
# Запустить все тесты
make test

# Тест API вручную
curl http://localhost:8001/api/v1/ping/
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi"}'
```

## 📊 Мониторинг и логи

```bash
# Просмотр логов
make logs

# Статус сервисов
make status

# Метрики Prometheus
curl http://localhost:9091/metrics

# Статистика Redis
make redis-cli
> INFO stats
```

## 🛡 Безопасность и производительность

### Встроенные функции
- ✅ Rate limiting (100 req/min по умолчанию)
- ✅ Structured logging
- ✅ Prometheus metrics
- ✅ Redis caching
- ✅ Async operations
- ✅ Health checks

### Мониторинг производительности
```bash
# Проверить метрики
curl http://localhost:8001/metrics

# Статистика кеша
curl http://localhost:8001/api/v1/cache/stats/

# Очистить кеш при необходимости
curl -X POST http://localhost:8001/api/v1/cache/clear/
```

## 🔄 Workflow автоматизации

### Автоматическая проверка при запуске

При выполнении `make start`:
- ✅ Запускаются все сервисы (API, БД, Redis)
- ✅ Ждет готовности сервисов  
- ✅ Автоматически проверяет здоровье системы
- ✅ Показывает статус подключения к cannamente

### Синхронизация данных

```bash
# Однократная синхронизация
make sync-cannamente

# Мониторинг новых данных (каждые 30 сек)
make watch-cannamente

# В фоне
nohup make watch-cannamente > sync.log 2>&1 &
```

## 📁 Структура проекта

```
ai_budtender/
├── app/                    # Исходный код приложения
│   ├── api/               # API endpoints
│   ├── core/              # Основная логика (RAG, LLM)
│   ├── db/                # База данных и модели
│   ├── models/            # Pydantic схемы
│   └── utils/             # Утилиты
├── scripts/               # Скрипты автоматизации
│   ├── sync_cannamente.py # Синхронизация данных
│   ├── watch_cannamente.py # Мониторинг новых данных
│   ├── check_db_connection.py # Проверка БД
│   └── init_db.sql        # Инициализация локальной БД
├── docker-compose.yml     # Docker конфигурация
├── Dockerfile            # Docker образ
├── Makefile             # Команды автоматизации
└── requirements.txt     # Python зависимости
```

## 📝 Changelog

### Текущая версия
- ✅ Локальная PostgreSQL с pgvector
- ✅ Синхронизация из cannamente (read-only)
- ✅ Structured logging (structlog)
- ✅ Redis caching
- ✅ Rate limiting
- ✅ Prometheus metrics
- ✅ Async operations
- ✅ Health checks
- ✅ Простой daily workflow

---

**🎯 Готово к использованию!** Выполни `make start` и начинай работу. 