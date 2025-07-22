# Простой флоу работы с AI Budtender

## 🚀 Ежедневный запуск (после перезагрузки)

```bash
# 1. Запустить cannamente (если не запущен)
cd ../cannamente && docker-compose up -d

# 2. Запустить AI Budtender
cd ai_budtender && make start
```

**Готово!** Теперь у вас:
- ✅ Локальная БД с pgvector (данные сохраняются)
- ✅ Автоматическая проверка здоровья системы
- ✅ Работающий API на http://localhost:8001

## 📊 Проверка работы

```bash
# Проверить статус всех сервисов
make status

# Проверить подключение к БД
make check-db

# Посмотреть логи
make logs

# Тест API
curl http://localhost:8001/api/v1/ping/
```

## 🔄 Синхронизация данных

### Первоначальная синхронизация
```bash
# Синхронизировать все данные из cannamente
make sync-cannamente
```

### Автоматический мониторинг новых данных
```bash
# Запустить в фоне (проверка каждые 30 секунд)
make watch-cannamente

# Или в отдельном терминале:
nohup make watch-cannamente > sync.log 2>&1 &
```

### Ручная синхронизация новых данных
```bash
# Синхронизировать только новые strains
make sync-new
```

## 🛑 Остановка

```bash
# Остановить AI Budtender
make stop

# Остановить cannamente
cd ../cannamente && docker-compose down
```

## 🎯 Тестирование API

```bash
# Тест чата
curl -X POST http://localhost:8001/api/v1/chat/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Recommend something for relaxation", "history": []}'

# Получить продукты
curl http://localhost:8001/api/v1/products/

# Очистить кеш
curl -X POST http://localhost:8001/api/v1/cache/clear/
```

## 🔧 Устранение проблем

### Проблема: БД не подключается
```bash
# Проверить cannamente
docker ps | grep canna

# Проверить подключение
make check-db

# Перезапустить
make restart
```

### Проблема: Нет данных
```bash
# Синхронизировать данные из cannamente
make sync-cannamente
```

### Проблема: Сервисы не запускаются
```bash
# Очистить и пересоздать
make clean
make start
```

## 📈 Мониторинг

```bash
# Статус сервисов
make status

# Логи в реальном времени
make logs

# Метрики
curl http://localhost:8001/metrics

# Статистика кеша
curl http://localhost:8001/api/v1/cache/stats/
```

## 💡 Полезные команды

```bash
# Открыть shell в контейнере
make shell

# Открыть Redis CLI
make redis-cli

# Запустить тесты
make test

# Форматировать код
make format
```

## 🔄 Архитектура

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
- ✅ Данные сохраняются после перезагрузки
- ✅ pgvector всегда доступен
- ✅ Быстрый векторный поиск
- ✅ Независимость от внешних сервисов
- ✅ Автоматическая проверка здоровья
- ✅ Простой флоу работы 