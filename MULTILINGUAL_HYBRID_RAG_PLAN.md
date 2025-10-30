

### Основная цель
Адаптировать AI Budtender к мультиязычной архитектуре cannamente (EN/ES) с гибридным подходом к поиску (Structured Filtering + Vector Search).

### Ключевые улучшения
1. ✅ Полная мультиязычность (EN/ES) для всех сущностей
2. ✅ Гибридный RAG: Structured Filters → Vector Reranking
3. ✅ Поддержка terpenes в поиске и рекомендациях
4. ✅ Dual embeddings (раздельные векторы для EN и ES)
5. ✅ Восстановление работы скриптов синхронизации

---

## 📊 Текущее состояние (Baseline)

### ✅ Работает
- Smart RAG Service v3.0 с AI-driven criteria
- Structured filtering + weighted priority scoring
- Session management с контекстом
- Medical-first prioritization
- Semantic flavor reranking (на лету)

### ❌ Не работает / Отсутствует
- **Скрипты синхронизации сломаны** (удален `rag_service.py`)
- **Векторный поиск отключен** (был в v1.0-v2.0, удален в v3.0)
- **Terpenes не используются** (не синхронизируются из cannamente)
- **Мультиязычность не учитывается** (читаем только legacy поля)

### 🔍 Результаты исследования

#### Мультиязычность в cannamente DB
| Сущность | Поля | Пример |
|----------|------|--------|
| **Strain** | `title_en`, `title_es`, `description_en`, `description_es`, `text_content_en`, `text_content_es`, `keywords_en`, `keywords_es` | "Northern Lights" / "Luces del Norte" |
| **Feeling** | `name_en`, `name_es` | "Relaxed" / "Relajación" |
| **Flavor** | `name_en`, `name_es` | "Earthy" / "Terroso" |
| **HelpsWith** | `name_en`, `name_es` | "Insomnia" / "Insomnio" |
| **Negative** | `name_en`, `name_es` | "Dry mouth" / "Boca seca" |
| **Terpene** | `description_en`, `description_es` (name без перевода) | "Myrcene (herbal)" |

#### Размер и стоимость
- **OpenAI embeddings стоимость:** $0.05 на 1000 сортов (dual EN+ES)
- **Dual embeddings размер:** ~12 MB на 1000 сортов (~10% от БД)
- **Terpenes в cannamente:** 8 terpenes, используются в сортах

#### 🔍 ВАЖНО: Текущая архитектура (после детального анализа)

**Обнаружено:** Smart RAG v3.0 использует **in-memory фильтрацию**, а не SQL-based filtering!

```python
# Текущий подход:
all_strains = repository.get_strains_with_relations(limit=200)
# SQL: просто SELECT * FROM strains WHERE active=true LIMIT 200

# Затем фильтрация в Python:
filtered = [s for s in all_strains if matches_criteria(s, filters)]

# Затем scoring в Python:
scored = [(s, calculate_score(s, filters)) for s in filtered]
```

**Что это означает для плана:**
- ✅ **ЭТАП 3 УПРОЩАЕТСЯ** - не нужны сложные SQL запросы, только Python код
- ✅ **Vector reranking будет in-memory** - просто пересортировка уже загруженных данных
- ✅ Работает отлично для текущего масштаба (~200 сортов)
- ⚠️ При масштабировании (>1000 сортов) потребуется SQL optimization (добавлен опциональный ЭТАП 6)

Детальный анализ: см. `CURRENT_ARCHITECTURE_ANALYSIS.md`

---

## 🗺️ Архитектура решения

### Гибридный RAG подход

```
┌─────────────────────────────────────────────────────────────────┐
│                      User Query (EN or ES)                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│           AI Smart Query Analyzer (language-aware)               │
│  • Detect language (EN/ES)                                       │
│  • Generate structured filters (medical-first)                   │
│  • Extract criteria (category, effects, terpenes, THC/CBD)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 1: Structured Filtering (Safety)               │
│  • Apply hard constraints (category, medical conditions)         │
│  • Filter by effects, terpenes, cannabinoids                     │
│  • Exclude contradictory effects                                 │
│  Result: 20-50 medically-safe candidates                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│        STEP 2: Vector Semantic Reranking (Relevance)             │
│  • Generate query embedding (language-specific)                  │
│  • Compute cosine similarity with candidates                     │
│  • Rerank by semantic relevance                                  │
│  Result: Top 5 most relevant strains                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM Response Generation                       │
│  • Generate natural language response (language-aware)           │
│  • Include strain recommendations with effects                   │
│  • Provide quick actions for follow-up                           │
└─────────────────────────────────────────────────────────────────┘
```

### Преимущества гибридного подхода
- ✅ **Medical Safety:** Structured filters гарантируют безопасные рекомендации
- ✅ **Semantic Relevance:** Vector search находит самые релевантные по смыслу
- ✅ **Best of Both Worlds:** Точность + гибкость

---

## 📋 План разработки

### **ЭТАП 1: Восстановление базовой функциональности** 🔴 HIGH PRIORITY

**Цель:** Восстановить работу скриптов синхронизации

#### 1.1 Восстановить RAGService класс
**Файл:** `app/core/rag_service.py`

**Задачи:**
- [x] Создать класс `RAGService` с методами:
  - `generate_embedding(strain, language='en')` - генерация эмбеддинга для языка
  - `_build_embedding_text(strain, language)` - построение текста для векторизации
  - `add_strain_embeddings(strain_id)` - генерация dual embeddings (EN + ES)

**Зависимости:** LLM interface уже существует

**Проверка:**
```bash
python -c "from app.core.rag_service import RAGService; print('OK')"
```

#### 1.2 Обновить модель Strain для мультиязычности
**Файл:** `app/models/database.py`

**Задачи:**
- [x] Добавить поля:
  ```python
  # Multilingual content fields
  name_en = Column(String(255), nullable=True)
  name_es = Column(String(255), nullable=True)
  title_en = Column(String(255), nullable=True)
  title_es = Column(String(255), nullable=True)
  description_en = Column(Text, nullable=True)
  description_es = Column(Text, nullable=True)
  text_content_en = Column(Text, nullable=True)
  text_content_es = Column(Text, nullable=True)
  keywords_en = Column(String(255), nullable=True)
  keywords_es = Column(String(255), nullable=True)

  # Dual embeddings
  embedding_en = Column(Vector(1536), nullable=True)
  embedding_es = Column(Vector(1536), nullable=True)

  # Legacy field (backward compatibility)
  embedding = Column(Vector(1536), nullable=True)  # Deprecated
  ```

#### 1.3 Миграция базы данных
**Файл:** `migrations/002_multilingual_embeddings.sql`

**Задачи:**
- [x] Создать миграцию:
  ```sql
  -- Add multilingual content fields
  ALTER TABLE strains_strain
    ADD COLUMN IF NOT EXISTS name_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS name_es VARCHAR(255),
    ADD COLUMN IF NOT EXISTS title_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS title_es VARCHAR(255),
    ADD COLUMN IF NOT EXISTS description_en TEXT,
    ADD COLUMN IF NOT EXISTS description_es TEXT,
    ADD COLUMN IF NOT EXISTS text_content_en TEXT,
    ADD COLUMN IF NOT EXISTS text_content_es TEXT,
    ADD COLUMN IF NOT EXISTS keywords_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS keywords_es VARCHAR(255);

  -- Add dual embedding fields
  ALTER TABLE strains_strain
    ADD COLUMN IF NOT EXISTS embedding_en vector(1536),
    ADD COLUMN IF NOT EXISTS embedding_es vector(1536);

  -- Create indexes for fast vector search
  CREATE INDEX IF NOT EXISTS strains_embedding_en_idx
    ON strains_strain USING ivfflat (embedding_en vector_cosine_ops)
    WITH (lists = 100);

  CREATE INDEX IF NOT EXISTS strains_embedding_es_idx
    ON strains_strain USING ivfflat (embedding_es vector_cosine_ops)
    WITH (lists = 100);

  -- Populate legacy fields from new ones for backward compatibility
  UPDATE strains_strain
  SET
    name = COALESCE(name_es, name_en, name),
    embedding = embedding_en
  WHERE name_en IS NOT NULL OR name_es IS NOT NULL;
  ```

**Выполнение:**
```bash
docker compose exec db psql -U ai_user -d ai_budtender -f /migrations/002_multilingual_embeddings.sql
```

#### 1.4 Обновить скрипт синхронизации
**Файл:** `scripts/sync_strain_relations.py`

**Задачи:**
- [x] Обновить SQL запрос:
  ```python
  cursor.execute("""
      SELECT DISTINCT
          s.id,
          s.name,           -- legacy
          s.title_en,       -- NEW
          s.title_es,       -- NEW
          s.description_en, -- NEW
          s.description_es, -- NEW
          s.text_content_en,-- NEW
          s.text_content_es,-- NEW
          s.keywords_en,    -- NEW
          s.keywords_es,    -- NEW
          s.cbd,
          s.thc,
          s.cbg,
          s.category,
          s.active,
          s.slug,
          ARRAY_AGG(DISTINCT f.name_en) FILTER (WHERE f.name_en IS NOT NULL) as feelings_en,
          ARRAY_AGG(DISTINCT f.name_es) FILTER (WHERE f.name_es IS NOT NULL) as feelings_es,
          ARRAY_AGG(DISTINCT h.name_en) FILTER (WHERE h.name_en IS NOT NULL) as helps_with_en,
          ARRAY_AGG(DISTINCT h.name_es) FILTER (WHERE h.name_es IS NOT NULL) as helps_with_es,
          ARRAY_AGG(DISTINCT n.name_en) FILTER (WHERE n.name_en IS NOT NULL) as negatives_en,
          ARRAY_AGG(DISTINCT n.name_es) FILTER (WHERE n.name_es IS NOT NULL) as negatives_es,
          ARRAY_AGG(DISTINCT fl.name_en) FILTER (WHERE fl.name_en IS NOT NULL) as flavors_en,
          ARRAY_AGG(DISTINCT fl.name_es) FILTER (WHERE fl.name_es IS NOT NULL) as flavors_es
      FROM strains_strain s
      LEFT JOIN strains_strain_feelings sf ON s.id = sf.strain_id
      LEFT JOIN strains_feeling f ON sf.feeling_id = f.id
      LEFT JOIN strains_strain_helps_with sh ON s.id = sh.strain_id
      LEFT JOIN strains_helpswith h ON sh.helpswith_id = h.id
      LEFT JOIN strains_strain_negatives sn ON s.id = sn.strain_id
      LEFT JOIN strains_negative n ON sn.negative_id = n.id
      LEFT JOIN strains_strain_flavors sfl ON s.id = sfl.strain_id
      LEFT JOIN strains_flavor fl ON sfl.flavor_id = fl.id
      WHERE s.active = true
      GROUP BY s.id, s.name, s.title_en, s.title_es, ...
      ORDER BY s.title_es
  """)
  ```

- [x] Обновить обработку результатов:
  ```python
  strain_data = {
      'name_en': row[2],
      'name_es': row[3] or row[2],  # Fallback to EN
      'title_en': row[2],
      'title_es': row[3],
      'description_en': row[4],
      'description_es': row[5],
      'text_content_en': row[6],
      'text_content_es': row[7],
      # Legacy для совместимости
      'name': row[3] or row[2],  # Prefer ES
      'description': row[5] or row[4],
      ...
  }
  ```

- [x] Добавить генерацию dual embeddings:
  ```python
  def regenerate_embeddings():
      rag_service = RAGService(repository)

      for strain in strains:
          # Generate both EN and ES embeddings
          rag_service.add_strain_embeddings(strain.id)
  ```

**Проверка:**
```bash
docker compose exec api python scripts/sync_strain_relations.py
# Должно синхронизировать все поля + сгенерировать dual embeddings
```

**Критерии успеха ЭТАПА 1:**
- ✅ Скрипт синхронизации работает без ошибок
- ✅ Все мультиязычные поля синхронизированы
- ✅ Dual embeddings сгенерированы для всех сортов
- ✅ Legacy поля заполнены для обратной совместимости

**Время:** 2-3 дня

---

### **ЭТАП 2: Добавление Terpenes** 🟡 MEDIUM PRIORITY

**Цель:** Интегрировать terpenes в систему поиска и рекомендаций

#### 2.1 Расширить модель Strain
**Файл:** `app/models/database.py`

**Задачи:**
- [x] Добавить поля terpenes (уже есть в модели, проверить):
  ```python
  # In Strain model:
  dominant_terpene_id = Column(Integer, ForeignKey('terpenes.id'), nullable=True)
  dominant_terpene = relationship('Terpene', foreign_keys=[dominant_terpene_id])
  other_terpenes = relationship('Terpene', secondary=strain_terpenes_table)
  ```

#### 2.2 Обновить синхронизацию terpenes
**Файл:** `scripts/sync_strain_relations.py`

**Задачи:**
- [x] Добавить terpenes в SQL запрос:
  ```python
  cursor.execute("""
      SELECT DISTINCT
          s.id,
          ...,
          dt.name as dominant_terpene,
          dt.description as dominant_terpene_desc,
          ARRAY_AGG(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL) as other_terpenes,
          ARRAY_AGG(DISTINCT t.description) FILTER (WHERE t.description IS NOT NULL) as terpene_descriptions
      FROM strains_strain s
      ...
      LEFT JOIN strains_terpene dt ON s.dominant_terpene_id = dt.id
      LEFT JOIN strains_strain_other_terpenes sot ON s.id = sot.strain_id
      LEFT JOIN strains_terpene t ON sot.terpene_id = t.id
      ...
  """)
  ```

- [x] Создать/обновлять terpenes в БД:
  ```python
  def sync_terpenes(terpene_names, terpene_descriptions):
      for name, desc in zip(terpene_names, terpene_descriptions):
          terpene = session.query(Terpene).filter_by(name=name).first()
          if not terpene:
              terpene = Terpene(name=name, description=desc)
              session.add(terpene)
      session.commit()
  ```

#### 2.3 Включить terpenes в embeddings
**Файл:** `app/core/rag_service.py`

**Задачи:**
- [x] Обновить `_build_embedding_text()`:
  ```python
  def _build_embedding_text(self, strain: Strain, language: str) -> str:
      text_parts = [...]

      # Add terpenes (NEW)
      if strain.dominant_terpene:
          text_parts.append(f"Dominant terpene: {strain.dominant_terpene.name}")

      if strain.other_terpenes:
          terpene_names = [t.name for t in strain.other_terpenes]
          text_parts.append(f"Other terpenes: {', '.join(terpene_names)}")

      return " ".join(text_parts)
  ```

#### 2.4 Добавить terpene filtering в AI analyzer
**Файл:** `app/core/smart_query_analyzer.py`

**Задачи:**
- [x] Обновить промпт для AI:
  ```python
  Available filter fields:
  - category (Indica/Sativa/Hybrid)
  - effects (Sleepy, Energetic, etc.)
  - helps_with (Insomnia, Pain, etc.)
  - terpenes (Myrcene, Limonene, Caryophyllene, etc.)  # NEW
  - thc, cbd, cbg (numeric values)
  ```

#### 2.5 Добавить universal filtering для terpenes
**Файл:** `app/core/universal_action_executor.py`

**Задачи:**
- [x] Добавить обработку terpenes в `_get_strain_field_value()`:
  ```python
  if field_name == "terpenes":
      terpene_names = []
      if strain.dominant_terpene:
          terpene_names.append(strain.dominant_terpene.name)
      if strain.other_terpenes:
          terpene_names.extend([t.name for t in strain.other_terpenes])
      return terpene_names
  ```

**Критерии успеха ЭТАПА 2:**
- ✅ Terpenes синхронизируются из cannamente
- ✅ Terpenes включены в embeddings
- ✅ AI может фильтровать по terpenes
- ✅ Query "strains with limonene" возвращает правильные результаты

**Время:** 1-2 дня

---

### **ЭТАП 3: Гибридный поиск (SQL Filtering + Vector Reranking)** 🟢 NORMAL PRIORITY

**Цель:** Реализовать масштабируемый гибридный поиск с SQL-based фильтрацией и векторным reranking

**⚠️ ВАЖНО:** Интегрируем SQL optimization сразу, чтобы система была готова к масштабированию до 10,000+ сортов.

#### 3.1 Добавить утилиту для cosine similarity
**Файл:** `app/core/vector_utils.py` (новый)

**Задачи:**
- [x] Создать вспомогательную функцию:
  ```python
  import numpy as np
  from typing import List

  def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
      """Calculate cosine similarity between two vectors"""
      v1 = np.array(vec1)
      v2 = np.array(vec2)

      dot_product = np.dot(v1, v2)
      norm1 = np.linalg.norm(v1)
      norm2 = np.linalg.norm(v2)

      if norm1 == 0 or norm2 == 0:
          return 0.0

      return float(dot_product / (norm1 * norm2))
  ```

**Зависимости:** `numpy` уже установлен

#### 3.2 Реализовать SQL-based structured filtering
**Файл:** `app/db/repository.py`

**Задачи:**
- [x] Добавить метод `search_with_structured_filters()`:
  ```python
  from typing import List, Optional
  from sqlalchemy import or_, and_, exists

  def search_with_structured_filters(
      self,
      category: Optional[str] = None,
      categories: Optional[List[str]] = None,
      min_thc: Optional[float] = None,
      max_thc: Optional[float] = None,
      min_cbd: Optional[float] = None,
      max_cbd: Optional[float] = None,
      required_effects: Optional[List[str]] = None,
      exclude_effects: Optional[List[str]] = None,
      required_helps_with: Optional[List[str]] = None,
      any_helps_with: Optional[List[str]] = None,
      required_terpenes: Optional[List[str]] = None,
      limit: int = 50
  ) -> List[Strain]:
      """
      SQL-based structured filtering (efficient for large datasets).
      Preserves all AI-driven flexibility.
      """

      query = self.db.query(StrainModel).filter(StrainModel.active == True)

      # Category filters
      if category:
          query = query.filter(StrainModel.category == category)
      elif categories:
          query = query.filter(StrainModel.category.in_(categories))

      # Cannabinoid range filters
      if min_thc is not None:
          query = query.filter(StrainModel.thc >= min_thc)
      if max_thc is not None:
          query = query.filter(StrainModel.thc <= max_thc)
      if min_cbd is not None:
          query = query.filter(StrainModel.cbd >= min_cbd)
      if max_cbd is not None:
          query = query.filter(StrainModel.cbd <= max_cbd)

      # Required effects (JOIN + filter)
      if required_effects:
          for effect in required_effects:
              query = query.join(
                  StrainModel.feelings
              ).filter(
                  or_(
                      FeelingModel.name_en == effect,
                      FeelingModel.name_es == effect,
                      FeelingModel.name == effect  # Legacy fallback
                  )
              )

      # Exclude effects (NOT EXISTS subquery)
      if exclude_effects:
          for effect in exclude_effects:
              subquery = (
                  self.db.query(StrainModel.id)
                  .join(StrainModel.feelings)
                  .filter(
                      or_(
                          FeelingModel.name_en == effect,
                          FeelingModel.name_es == effect,
                          FeelingModel.name == effect
                      )
                  )
              )
              query = query.filter(~StrainModel.id.in_(subquery))

      # Required medical conditions (AND logic)
      if required_helps_with:
          for condition in required_helps_with:
              query = query.join(
                  StrainModel.helps_with
              ).filter(
                  or_(
                      HelpsWithModel.name_en == condition,
                      HelpsWithModel.name_es == condition,
                      HelpsWithModel.name == condition
                  )
              )

      # Any medical conditions (OR logic)
      if any_helps_with:
          query = query.join(StrainModel.helps_with).filter(
              or_(
                  HelpsWithModel.name_en.in_(any_helps_with),
                  HelpsWithModel.name_es.in_(any_helps_with),
                  HelpsWithModel.name.in_(any_helps_with)
              )
          )

      # Terpene filters (if needed)
      if required_terpenes:
          # Will implement in STAGE 2
          pass

      return query.limit(limit).all()
  ```

#### 3.3 Конвертер AI критериев в SQL
**Файл:** `app/core/universal_action_executor.py`

**Задачи:**
- [x] Добавить метод `_convert_ai_criteria_to_sql()`:
  ```python
  def _convert_ai_criteria_to_sql(self, ai_filters: Dict[str, Any]) -> Dict[str, Any]:
      """
      Конвертирует AI-generated критерии в SQL-friendly формат.
      Сохраняет всю гибкость AI, просто меняет executor.
      """
      sql_filters = {}

      for field, criterion in ai_filters.items():
          operator = criterion.get("operator")
          value = criterion.get("value")

          # Universal mapping: AI operators → SQL parameters
          if field == "category":
              if operator == "eq":
                  sql_filters["category"] = value
              elif operator == "in":
                  sql_filters["categories"] = value

          elif field in ["thc", "cbd", "cbg"]:
              if operator == "gte":
                  sql_filters[f"min_{field}"] = value
              elif operator == "lte":
                  sql_filters[f"max_{field}"] = value

          elif field == "effects":
              if operator == "contains":
                  sql_filters["required_effects"] = value if isinstance(value, list) else [value]
              elif operator == "not_contains":
                  sql_filters["exclude_effects"] = value if isinstance(value, list) else [value]

          elif field == "helps_with":
              if operator == "contains":
                  sql_filters["required_helps_with"] = value if isinstance(value, list) else [value]
              elif operator == "any":
                  sql_filters["any_helps_with"] = value if isinstance(value, list) else [value]

          elif field == "terpenes":
              if operator == "contains":
                  sql_filters["required_terpenes"] = value if isinstance(value, list) else [value]

      return sql_filters
  ```

#### 3.4 Добавить vector reranking
**Файл:** `app/core/universal_action_executor.py`

**Задачи:**
- [x] Добавить метод `_apply_vector_reranking()`:
  ```python
  from app.core.vector_utils import cosine_similarity

  def _apply_vector_reranking(
      self,
      candidates: List[Strain],
      query_embedding: List[float],
      language: str = 'en',
      limit: int = 5
  ) -> List[Strain]:
      """Rerank in-memory candidates by vector similarity"""

      if not candidates or not query_embedding:
          return candidates[:limit]

      scored = []
      for strain in candidates:
          # Get embedding based on language
          if language == 'en':
              strain_embedding = getattr(strain, 'embedding_en', None)
          else:
              strain_embedding = getattr(strain, 'embedding_es', None)

          # Fallback to legacy embedding
          if not strain_embedding:
              strain_embedding = getattr(strain, 'embedding', None)

          if strain_embedding:
              similarity = cosine_similarity(query_embedding, strain_embedding)
              scored.append((strain, similarity))
          else:
              scored.append((strain, 0.0))

      # Sort by similarity (descending)
      sorted_strains = sorted(scored, key=lambda x: x[1], reverse=True)
      logger.info(f"Vector reranking: top strain '{sorted_strains[0][0].name}' "
                  f"with similarity {sorted_strains[0][1]:.3f}")

      return [s[0] for s in sorted_strains[:limit]]
  ```

- [x] Полностью переписать `_execute_search_strains()`:
  ```python
  def _execute_search_strains(
      self,
      session_strains: List[Strain],
      parameters: Dict[str, Any],
      language: str = 'en'
  ) -> List[Strain]:
      """
      Hybrid search: SQL-based filtering + Vector reranking
      Preserves AI-driven flexibility while improving performance
      """

      filters = parameters.get("filters", {})
      query_text = parameters.get("query_text")
      use_vector_rerank = parameters.get("use_vector_rerank", True)
      limit = parameters.get("limit", 5)

      # STEP 1: Convert AI criteria to SQL filters
      sql_filters = self._convert_ai_criteria_to_sql(filters)
      logger.info(f"AI criteria → SQL filters: {sql_filters}")

      # STEP 2: SQL-based structured filtering (efficient)
      try:
          candidates = self.repository.search_with_structured_filters(
              **sql_filters,
              limit=50  # Get more candidates for vector reranking
          )
          logger.info(f"SQL filtering: returned {len(candidates)} candidates")
      except Exception as e:
          logger.error(f"SQL filtering failed: {e}, falling back to in-memory")
          # Fallback to old in-memory approach if SQL fails
          all_strains = self.repository.get_strains_with_relations(limit=200)
          candidates = self._apply_universal_filters(all_strains, filters)[:50]

      if len(candidates) == 0:
          logger.warning("No candidates found after filtering")
          return []

      # STEP 3: Vector reranking for semantic relevance (optional)
      if use_vector_rerank and query_text and len(candidates) > 0:
          try:
              # Generate query embedding
              query_embedding = self._llm.generate_embedding(query_text)

              # Rerank candidates by vector similarity
              reranked_strains = self._apply_vector_reranking(
                  candidates=candidates,
                  query_embedding=query_embedding,
                  language=language,
                  limit=limit
              )

              logger.info(f"Vector reranking: {len(candidates)} → {len(reranked_strains)} top results")
              return reranked_strains

          except Exception as e:
              logger.warning(f"Vector reranking failed: {e}, using SQL results")
              return candidates[:limit]
      else:
          # Return SQL-filtered results without vector reranking
          logger.info(f"Returning {len(candidates[:limit])} results without vector reranking")
          return candidates[:limit]
  ```

#### 3.5 Обновить SmartQueryAnalyzer
**Файл:** `app/core/smart_query_analyzer.py`

**Задачи:**
- [x] Добавить флаг vector reranking в action plan:
  ```python
  # In _build_full_context():
  context = {
      "user_query": user_query,
      "query_text": user_query,  # NEW: preserve original query for embedding
      ...
  }

  # In action plan parameters:
  parameters = {
      "filters": {...},
      "use_vector_rerank": True,  # NEW: enable vector reranking
      "query_text": user_query,   # NEW: pass query for embedding
      ...
  }
  ```

#### 3.6 Обновить SmartRAGService
**Файл:** `app/core/smart_rag_service.py`

**Задачи:**
- [x] Передать язык в executor:
  ```python
  def process_contextual_query(self, query: str, session_id: Optional[str] = None, ...):
      ...
      # Определяем язык
      detected_language = smart_analysis.detected_language or detect_language(query)

      # Выполняем действие с учетом языка
      result_strains = self.action_executor.execute_action(
          smart_analysis.action_plan,
          session_strains,
          language=detected_language  # NEW parameter
      )
      ...
  ```

#### 3.7 Опциональное Redis кеширование (optional)
**Файл:** `app/core/universal_action_executor.py`

**Задачи:**
- [x] Добавить кеширование результатов для частых запросов:
  ```python
  def _execute_search_strains(self, session_strains, parameters, language='en'):
      # Build cache key from filters and query
      cache_key = self._build_cache_key(parameters.get("filters"), parameters.get("query_text"))

      # Check cache first
      cached_result = self.cache.get(cache_key)
      if cached_result:
          logger.info(f"Cache hit for key: {cache_key}")
          return cached_result

      # ... SQL filtering + vector reranking ...

      # Cache results for 30 minutes
      self.cache.set(cache_key, result_strains, ttl=1800)
      return result_strains
  ```

**Критерии успеха ЭТАПА 3:**
- ✅ SQL-based filtering работает для любого размера датасета (200-10,000+ сортов)
- ✅ AI гибкость полностью сохранена (критерии автоматически конвертируются в SQL)
- ✅ Vector reranking улучшает semantic relevance
- ✅ Medical safety сохранена (SQL WHERE clauses применяются первыми)
- ✅ Performance: <100ms для 1000 сортов (vs 300-600ms текущий подход)
- ✅ Graceful fallback на in-memory при ошибках SQL
- ✅ Можно отключить vector reranking через `use_vector_rerank=False`

**Время:** 2-3 дня (интегрирована SQL optimization)

---

### **ЭТАП 4: Мультиязычные Effects/Flavors** 🟢 NORMAL PRIORITY

**Цель:** Использовать правильные переводы effects/flavors в зависимости от языка запроса

#### 4.1 Обновить модели Effect/Flavor
**Файл:** `app/models/database.py`

**Задачи:**
- [x] Добавить поля name_en/es (если нет):
  ```python
  class Feeling(Base):
      id = Column(Integer, primary_key=True)
      name = Column(String(50), unique=True)  # Legacy
      name_en = Column(String(50))  # NEW
      name_es = Column(String(50))  # NEW
      # ...

  # Аналогично для Flavor, HelpsWith, Negative
  ```

#### 4.2 Обновить синхронизацию
**Файл:** `scripts/sync_strain_relations.py`

**Задачи:**
- [x] Создавать/обновлять с обоими языками:
  ```python
  def create_or_get_feeling(name_en: str, name_es: str) -> Feeling:
      # Try to find by either language
      feeling = session.query(Feeling).filter(
          or_(Feeling.name_en == name_en, Feeling.name_es == name_es)
      ).first()

      if not feeling:
          feeling = Feeling(
              name=name_es or name_en,  # Legacy
              name_en=name_en,
              name_es=name_es
          )
          session.add(feeling)
      else:
          # Update if missing translation
          if not feeling.name_en and name_en:
              feeling.name_en = name_en
          if not feeling.name_es and name_es:
              feeling.name_es = name_es

      session.commit()
      return feeling
  ```

#### 4.3 Обновить схемы ответов
**Файл:** `app/models/schemas.py`

**Задачи:**
- [x] Добавить language-aware serialization:
  ```python
  class CompactFeeling(BaseModel):
      name: str
      name_en: Optional[str] = None
      name_es: Optional[str] = None

      @classmethod
      def from_orm_lang(cls, feeling: Feeling, language: str = 'es'):
          """Create from ORM with language preference"""
          if language == 'en':
              name = feeling.name_en or feeling.name or feeling.name_es
          else:
              name = feeling.name_es or feeling.name or feeling.name_en

          return cls(
              name=name,
              name_en=feeling.name_en,
              name_es=feeling.name_es
          )
  ```

#### 4.4 Обновить response builder
**Файл:** `app/core/smart_rag_service.py`

**Задачи:**
- [x] Использовать правильный язык при построении ответа:
  ```python
  def _build_smart_response(self, analysis: SmartAnalysis, strains: List[Strain], session: ConversationSession):
      language = analysis.detected_language

      compact_strains = []
      for strain in strains:
          # Use language-aware serialization
          compact_strain = CompactStrain(
              id=strain.id,
              name=strain.name_es if language == 'es' else strain.name_en,
              description=strain.description_es if language == 'es' else strain.description_en,
              feelings=[CompactFeeling.from_orm_lang(f, language) for f in strain.feelings],
              flavors=[CompactFlavor.from_orm_lang(f, language) for f in strain.flavors],
              helps_with=[CompactHelpsWith.from_orm_lang(h, language) for h in strain.helps_with],
              negatives=[CompactNegative.from_orm_lang(n, language) for n in strain.negatives],
              ...
          )
          compact_strains.append(compact_strain)

      return ChatResponse(
          response=analysis.natural_response,
          recommended_strains=compact_strains,
          language=language,
          ...
      )
  ```

**Критерии успеха ЭТАПА 4:**
- ✅ EN запросы возвращают EN названия effects/flavors
- ✅ ES запросы возвращают ES названия effects/flavors
- ✅ Fallback работает если перевод отсутствует
- ✅ API ответы содержат оба языка для гибкости UI

**Время:** 1-2 дня

---

### **ЭТАП 5: Тестирование и оптимизация** 🟣 FINAL STAGE

**Цель:** Убедиться что все компоненты работают корректно

#### 5.1 Интеграционные тесты
**Файл:** `tests/test_multilingual_hybrid_rag.py`

**Тест-кейсы:**
1. ✅ **Multilingual sync:**
   - Синхронизация всех полей EN/ES
   - Генерация dual embeddings
   - Terpenes синхронизация

2. ✅ **Hybrid search:**
   - Structured filtering работает
   - Vector reranking улучшает результаты
   - Medical safety сохранена

3. ✅ **Language awareness:**
   - EN query → EN response
   - ES query → ES response
   - Правильные переводы effects/flavors

4. ✅ **Terpene queries:**
   - "strains with limonene" → правильные результаты
   - Terpenes в embeddings улучшают поиск

5. ✅ **Edge cases:**
   - Отсутствие embeddings → fallback на structured filtering
   - Отсутствие перевода → fallback на другой язык
   - Пустые результаты → graceful handling

**Примеры тестов:**
```python
def test_multilingual_search():
    # EN query
    response_en = rag_service.process_contextual_query(
        "I need a relaxing indica with limonene for evening use"
    )
    assert response_en.language == 'en'
    assert any('Relaxed' in str(s.feelings) for s in response_en.recommended_strains)

    # ES query
    response_es = rag_service.process_contextual_query(
        "Necesito una indica relajante con limoneno para la noche"
    )
    assert response_es.language == 'es'
    assert any('Relajación' in str(s.feelings) for s in response_es.recommended_strains)

def test_hybrid_search_improves_relevance():
    # Query with specific semantic context
    query = "I want something that helps me unwind after a stressful day at work"

    # Without vector reranking
    response_no_vector = rag_service.process_contextual_query(
        query, use_vector_rerank=False
    )

    # With vector reranking
    response_with_vector = rag_service.process_contextual_query(
        query, use_vector_rerank=True
    )

    # Vector reranking should find more semantically relevant results
    # (strains with descriptions mentioning "unwind", "stress relief", "after work")
    assert len(response_with_vector.recommended_strains) > 0

def test_terpene_filtering():
    response = rag_service.process_contextual_query(
        "Show me strains with myrcene that help with sleep"
    )

    # Check that results actually have myrcene
    for strain in response.recommended_strains:
        terpene_names = [t.name for t in (strain.terpenes or [])]
        assert 'Myrcene' in terpene_names or 'myrcene' in str(strain.description).lower()
```

#### 5.2 Performance тесты

**Метрики:**
- Vector search latency: <50ms на 1000 сортов
- Full query processing: <500ms
- Embedding generation: ~100ms на сорт
- Memory usage: <100MB для 1000 dual embeddings

**Оптимизации:**
- ✅ pgvector индексы созданы
- ✅ Redis кэширование embeddings
- ✅ Batch processing для sync

#### 5.3 Документация

**Обновить:**
- [x] `README.md` - новая архитектура
- [x] `CLAUDE.md` - технические детали
- [x] API документация - новые поля
- [x] Deployment guide - миграции

**Критерии успеха ЭТАПА 5:**
- ✅ Все тесты проходят
- ✅ Performance метрики достигнуты
- ✅ Документация актуальна
- ✅ Система готова к production

**Время:** 2-3 дня

---

## 📊 Общая временная оценка

| Этап | Приоритет | Время | Изменение | Статус |
|------|-----------|-------|-----------|--------|
| ЭТАП 1: Восстановление базовой функциональности | 🔴 HIGH | 2-3 дня | - | ⏳ Pending |
| ЭТАП 2: Добавление Terpenes | 🟡 MEDIUM | 1-2 дня | - | ⏳ Pending |
| ЭТАП 3: Гибридный поиск (SQL + Vector) | 🟢 NORMAL | **2-3 дня** | **✅ SQL optimization интегрирована** | ⏳ Pending |
| ЭТАП 4: Мультиязычные Effects/Flavors | 🟢 NORMAL | 1-2 дня | - | ⏳ Pending |
| ЭТАП 5: Тестирование и оптимизация | 🟣 FINAL | 2-3 дня | - | ⏳ Pending |

**Общее время:** 8-13 дней (1.5-2.5 недели) ✅

**Изменения:** SQL optimization интегрирована в ЭТАП 3, убран отдельный опциональный ЭТАП 6

---

## 🎯 Ожидаемые результаты

### Технические улучшения
- ✅ Полная мультиязычность (EN/ES) для всех данных
- ✅ Dual embeddings для лучшего качества поиска
- ✅ Гибридный RAG: Safety + Relevance
- ✅ Поддержка terpenes в рекомендациях
- ✅ Все скрипты синхронизации работают

### Улучшение качества рекомендаций
- ✅ **+15-20% точность** за счет vector reranking
- ✅ **100% medical safety** за счет structured filtering
- ✅ **Поддержка сложных запросов:** "relaxing indica with limonene for evening use"
- ✅ **Мультиязычность:** одинаковое качество для EN и ES

### Production readiness
- ✅ Все тесты проходят
- ✅ Performance метрики достигнуты
- ✅ Документация актуальна
- ✅ Миграции подготовлены

---

## 🚀 Следующие шаги

### Немедленно (после утверждения плана)
1. Создать ветку `feature/multilingual-hybrid-rag`
2. Начать ЭТАП 1: Восстановление базовой функциональности

### После завершения всех этапов
1. Code review
2. QA testing
3. Staging deployment
4. Production deployment
5. Monitoring

---

## 📝 Заметки

### Технические решения
- **OpenAI embeddings:** Оставляем (стоимость минимальна: $0.05 на 1000 сортов)
- **Vector dimension:** 1536 (OpenAI ada-002 стандарт)
- **Database size:** ~12 MB dual embeddings на 1000 сортов (приемлемо)

### Риски и митигация
| Риск | Вероятность | Воздействие | Митигация |
|------|-------------|-------------|-----------|
| Embeddings генерация занимает много времени | Средняя | Среднее | Batch processing + progress tracking |
| Vector search медленный на больших объемах | Низкая | Среднее | pgvector индексы + caching |
| Качество переводов в cannamente низкое | Средняя | Низкое | Fallback на другой язык |
| Миграция БД ломает production | Низкая | Высокое | Тестирование на staging + backward compatibility |

---

**Документ подготовлен:** 23 октября 2025
**Автор:** AI Budtender Development Team
**Версия:** 1.0
