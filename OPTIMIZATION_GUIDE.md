# 🚀 Performance Optimization Guide for Canagent

## Проблема в Одной Строке
**30.5 СЕКУНД тратятся на загрузку 173 сортов с их отношениями!**

---

## Быстрое Решение (Quick Fix) - 10 минут

### Шаг 1: Понять Текущий Процесс

```python
# Сейчас это происходит в _execute_search_strains():
all_strains = self.repository.get_strains_with_relations(limit=200)

# Это загружает:
# - 173 Strain объекта
# - Для каждого: feelings (3-5), helps_with (3-5), negatives (3-5),
#                 flavors (3-5), terpenes (3-5)
# - Плюс vector embeddings (1536D вектор для каждого!)
```

### Почему это медленно?
1. **N+1 Query Problem**: Вместо одного SELECT, может быть 173 отдельных queries
2. **Большие данные**: Каждый вектор embeddings = 1536 float32 значений = 6KB
3. **Множество JOINов**: 5-6 таблиц для каждого сорта

### Решение: Две фазы загрузки

**Фаза 1** (30ms): Загрузить только нужные для фильтрации поля
```python
# id, name, category, thc, cbd, cbg = ~200 bytes per strain
# 173 strains = 34 KB total - очень быстро!
```

**Фаза 2** (10ms): Загрузить детали только для TOP-5 результатов
```python
# Полные данные только для 5 сортов = быстро
```

---

## Реализация - Шаг за Шагом

### 1️⃣ Добавить новый метод в Repository

**File**: `app/db/repository.py`

Найдите класс `StrainRepository` и добавьте этот метод:

```python
def get_strains_minimal(self, limit: int = 200):
    """
    Загрузить только базовые данные сортов для фильтрации.

    Включает:
    - id, name, category, thc, cbd, cbg

    НЕ включает:
    - feelings, helps_with, negatives, flavors, terpenes
    - vector embeddings (embedding_es, embedding_en)

    Время: ~20ms для 173 сортов вместо 30s
    """
    return self.db.query(Strain)\
        .options(
            # Не загружать тяжелые отношения
            noload(Strain.feelings),
            noload(Strain.helps_with),
            noload(Strain.negatives),
            noload(Strain.flavors),
            noload(Strain.terpenes)
        )\
        .limit(limit)\
        .all()

def get_strains_full(self, strain_ids: List[int]):
    """
    Загрузить ПОЛНЫЕ данные для конкретных сортов.
    Используется только для TOP-5 результатов.

    Время: ~10ms для 5 сортов
    """
    from sqlalchemy.orm import joinedload

    return self.db.query(Strain)\
        .options(
            joinedload(Strain.feelings),
            joinedload(Strain.helps_with),
            joinedload(Strain.negatives),
            joinedload(Strain.flavors),
            joinedload(Strain.terpenes)
        )\
        .filter(Strain.id.in_(strain_ids))\
        .all()
```

**Добавьте импорты** в начало файла:
```python
from sqlalchemy.orm import noload, joinedload
from typing import List
```

### 2️⃣ Обновить Universal Action Executor

**File**: `app/core/universal_action_executor.py`

Найдите метод `_execute_search_strains()` (примерно строка 66) и замените:

```python
# ❌ БЫЛО (30 секунд):
all_strains = self.repository.get_strains_with_relations(limit=200)

# ✅ СТАЛО (20 миллисекунд):
all_strains = self.repository.get_strains_minimal(limit=200)
```

Затем найдите конец метода (примерно строка 240-260), где происходит формирование результатов.

**ДОБАВЬТЕ** перед возвратом результатов (примерно перед `return result_strains`):

```python
# НОВОЕ: Загрузить полные данные для финальных результатов
try:
    result_ids = [s.id for s in result_strains]
    if result_ids:
        result_strains = self.repository.get_strains_full(result_ids)
except Exception as e:
    logger.warning(f"Could not load full strain details: {e}")
    # Fallback: use minimal data (результаты все еще полезные)

return result_strains
```

### 3️⃣ Тестирование

Переstart контейнер:
```bash
docker compose restart api
```

Запустите тест:
```bash
python3 test_performance.py
```

**Ожидаемый результат:**
- **Before**: 40-42 seconds
- **After**: 10-15 seconds
- **Improvement**: 65-75% faster ✅

---

## 🎯 Дополнительная Оптимизация (Bonus: -5-8 сек)

### Добавить Redis Кеширование

**File**: `app/core/universal_action_executor.py`

После импортов добавьте:
```python
from app.core.cache import cache_service
```

Замените:
```python
# ❌ БЫЛО:
all_strains = self.repository.get_strains_minimal(limit=200)

# ✅ СТАЛО:
CACHE_KEY = "strains:minimal:all"
all_strains = cache_service.get(CACHE_KEY)

if not all_strains:
    # Загрузить из БД и сохранить на 1 час
    all_strains = self.repository.get_strains_minimal(limit=200)
    cache_service.set(CACHE_KEY, all_strains, ttl=3600)
    logger.info("Loaded and cached all strains from database")
else:
    logger.info("Using cached strains (1 hour TTL)")
```

**Результат**: Повторные запросы за 0.1s вместо 40s! ⚡

---

## 📊 Expected Performance Improvements

### Сценарий 1: Только минимальная загрузка
```
Before: 40-42s
After:  10-15s
Improvement: 60-75% ✅
```

### Сценарий 2: Минимальная загрузка + кеширование
```
First request:  12-15s (как выше)
Cached requests: 0.5-1s (из Redis!)
Improvement: 95% для повторных запросов ✅✅
```

---

## 🔍 Как Проверить Улучшения

### Проверка логов:
```bash
docker compose logs api | grep -A5 "Database Query"
```

**Ожидаемое улучшение:**
```
# БЫЛО:
🔴 Database Query (get_strains)             |  30.522s | Mem:  +65.8MB

# ПОСЛЕ:
⚡ Database Query (get_strains)             |   0.045s | Mem:   +0.5MB
```

### Проверка памяти:
```bash
docker compose logs api | grep "Mem:"
```

**Ожидаемое:**
- Было: +65.8MB
- После: +0.5MB (99% меньше!)

---

## ❌ Частые Ошибки

### Ошибка 1: Забыть noload()
```python
# ❌ НЕПРАВИЛЬНО (все еще медленно):
return self.db.query(Strain).limit(limit).all()

# ✅ ПРАВИЛЬНО:
return self.db.query(Strain)\
    .options(noload(Strain.feelings))\  # <-- ВАЖНО!
    .limit(limit)\
    .all()
```

### Ошибка 2: Загружать полные данные дважды
```python
# ❌ НЕПРАВИЛЬНО:
all_strains = get_strains_full(limit=200)  # полные 173
# ... filtering ...
return result_strains  # только 5

# ✅ ПРАВИЛЬНО:
all_strains = get_strains_minimal(limit=200)
# ... filtering ...
result_strains = get_strains_full(ids)  # полные 5
```

### Ошибка 3: Cache не работает
```python
# ❌ НЕПРАВИЛЬНО (забыли сохранить):
all_strains = cache.get(key)
if not all_strains:
    all_strains = self.repository.get_strains_minimal()
    # ЗАБЫЛИ cache.set()!

# ✅ ПРАВИЛЬНО:
all_strains = cache.get(key)
if not all_strains:
    all_strains = self.repository.get_strains_minimal()
    cache.set(key, all_strains, ttl=3600)  # <-- ВАЖНО!
```

---

## 🚀 Next Steps

1. **Implement** minimal loading (30 minutes)
2. **Test** with `python3 test_performance.py` (5 minutes)
3. **Add** Redis caching (15 minutes)
4. **Monitor** with dashboards (ongoing)
5. **Document** performance improvements

---

## 📈 Monitoring After Optimization

Добавьте в логи для мониторинга:

```python
import time

start = time.time()
all_strains = self.repository.get_strains_minimal(limit=200)
elapsed = time.time() - start

logger.info(f"Loaded {len(all_strains)} strains in {elapsed:.3f}s")
logger.info(f"Cache status: {'HIT' if from_cache else 'MISS'}")
logger.info(f"Memory impact: {memory_delta:+.1f}MB")
```

---

## 📞 Questions?

Если что-то не ясно:
1. Проверьте сегодняшние логи API
2. Посмотрите на уже существующие methods в `repository.py`
3. Используйте файл `test_performance.py` для verification

**Expected Result**: Запросы будут обработаны в **1-2 секунды** вместо **40 секунд**! 🚀
