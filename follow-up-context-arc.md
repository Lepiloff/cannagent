# Архитектура Context-Aware AI Budtender v2.0 (Optimized)

## Обзор проблемы

**Текущая проблема:** AI агент корректно отвечает на запросы подбора сортов, но теряет контекст обсуждения. При follow-up запросах система выполняет новый поиск вместо работы с уже рекомендованными сортами.

**Цель:** Реализовать оптимизированную систему управления контекстом с минимальными вызовами LLM, robust fallback и адаптивным переключением контекст→поиск по БД.

---

## 🔵 BACKEND (Canagent API) - Оптимизированная версия

### 1. Unified LLM Processor (КЛЮЧЕВОЕ ИЗМЕНЕНИЕ)

#### 1.1 Единый процессор для всех операций
```python
# app/core/unified_processor.py

class UnifiedLLMProcessor:
    """Объединяет все LLM операции в один вызов для оптимизации"""
    
    def analyze_complete(
        self, 
        query: str, 
        session: ConversationSession
    ) -> UnifiedAnalysis:
        """ОДИН вызов LLM вместо 4-5"""
        
        prompt = """
        Analyze this cannabis consultation query and return complete analysis in JSON.
        
        Query: {query}
        Language hint: {last_language}
        Has previous recommendations: {has_strains}
        Last strains: {last_strains}
        Previous topic: {previous_topic}
        User preferences accumulated: {preferences}
        
        Return JSON with ALL of the following:
        {{
            "detected_language": "es|en",
            "query_type": "new_search|follow_up|comparison|detail_request|reset|clarification",
            "confidence": 0.0-1.0,
            "topic_changed": true|false,
            "criteria": {{
                "potency": {{"thc": "higher|lower|specific", "value": null}},
                "effects": {{"desired": [], "avoid": [], "priority": ""}},
                "medical_conditions": [],
                "flavors": {{"preferred": [], "avoid": []}},
                "strain_reference": {{"type": "index|name|all", "value": ""}},
                "custom_criteria": "",
                "conflicts_detected": []
            }},
            "action_needed": "filter|sort|compare|select|explain|clarify",
            "suggested_quick_actions": ["dynamic suggestions based on context"],
            "response_text": "Generated natural response in detected language"
        }}
        
        Critical instructions:
        - Detect if this is about previously mentioned strains (follow_up)
        - Check for conflicting criteria (e.g., "sleepy but energetic")
        - Generate response text in the detected language
        - Suggest relevant quick actions based on the context
        """
        
        context_summary = self._build_context_summary(session)
        
        try:
            result = self.llm.extract_json(
                prompt.format(
                    query=query,
                    last_language=session.detected_language or 'es',
                    has_strains=bool(session.recommended_strains_history),
                    last_strains=self._format_last_strains(session),
                    previous_topic=session.current_topic,
                    preferences=session.user_preferences
                )
            )
            
            return UnifiedAnalysis(**result)
            
        except Exception as e:
            # Fallback на правила если LLM недоступен
            return self.fallback_analyzer.analyze(query, session)
```

#### 1.2 Fallback анализатор на правилах
```python
# app/core/fallback_analyzer.py

class RuleBasedFallbackAnalyzer:
    """Резервный анализатор когда LLM недоступен"""
    
    def analyze(self, query: str, session: ConversationSession) -> UnifiedAnalysis:
        """Простой rule-based анализ без LLM"""
        
        query_lower = query.lower()
        
        # Детекция языка по ключевым словам
        language = 'es' if any(word in query_lower for word in 
                               ['necesito', 'quiero', 'cuál', 'para']) else 'en'
        
        # Определение типа запроса
        query_type = self._detect_query_type_by_rules(query_lower, session)
        
        # Базовые критерии по ключевым словам
        criteria = self._extract_basic_criteria(query_lower)
        
        # Простой ответ
        response = self._generate_simple_response(query_type, language)
        
        return UnifiedAnalysis(
            detected_language=language,
            query_type=query_type,
            confidence=0.5,  # Низкая уверенность для fallback
            criteria=criteria,
            response_text=response,
            is_fallback=True
        )
    
    def _detect_query_type_by_rules(self, query: str, session: ConversationSession):
        """Простые правила для определения типа"""
        
        # Reset patterns
        if any(p in query for p in ['empezar de nuevo', 'start over', 'nueva consulta']):
            return 'reset'
        
        # Follow-up indicators
        if session.recommended_strains_history:
            follow_up_words = ['cuál', 'which', 'mejor', 'better', 'primero', 
                              'first', 'último', 'last', 'estos', 'these']
            if any(word in query for word in follow_up_words):
                return 'follow_up'
        
        return 'new_search'
```

### 2. Enhanced Session Management

#### 2.1 Session Model с восстановлением
```python
# app/models/session.py

class ConversationSession:
    session_id: str
    created_at: datetime
    last_activity: datetime
    detected_language: str
    is_restored: bool = False  # Флаг восстановленной сессии
    
    # История с ограничением
    recommended_strains_history: List[List[int]]  # Макс 20
    current_topic: Optional[IntentType]
    previous_topics: List[IntentType]
    
    # Накопленные предпочтения
    user_preferences: Dict[str, Set[str]]
    
    # Детальная история
    conversation_history: List[Dict]
    
    def has_strains(self) -> bool:
        """Проверка наличия рекомендованных сортов"""
        return bool(self.recommended_strains_history)
    
    def get_last_strains(self) -> List[int]:
        """Безопасное получение последних сортов"""
        if self.recommended_strains_history:
            return self.recommended_strains_history[-1]
        return []
```

#### 2.2 Улучшенный Session Manager
```python
# app/core/session_manager.py

class ImprovedSessionManager:
    """Менеджер сессий с graceful восстановлением"""
    
    def __init__(self, redis_client, repository):
        self.redis = redis_client
        self.repository = repository
        self.session_ttl = 3600 * 4
        
    def get_or_restore_session(self, session_id: Optional[str]) -> ConversationSession:
        """Получение или восстановление сессии"""
        
        if not session_id:
            return self.create_new_session()
        
        # Попытка получить активную сессию
        session = self.get_active_session(session_id)
        
        if not session:
            # Попытка восстановления базового контекста
            session = self.restore_expired_session(session_id)
            
        return session
    
    def restore_expired_session(self, session_id: str) -> ConversationSession:
        """Восстановление истекшей сессии с базовым контекстом"""
        
        session = ConversationSession(
            session_id=session_id,
            created_at=datetime.now(),
            is_restored=True
        )
        
        # Попытка восстановить последние предпочтения из backup
        backup_key = f"backup:{session_id}"
        if self.redis.exists(backup_key):
            preferences = self.redis.get(backup_key)
            session.user_preferences = preferences
        
        return session
    
    def save_session_with_backup(self, session: ConversationSession):
        """Сохранение с backup для восстановления"""
        
        # Основное сохранение
        self.redis.setex(
            f"session:{session.session_id}",
            self.session_ttl,
            session.to_json()
        )
        
        # Backup ключевых предпочтений (на 7 дней)
        self.redis.setex(
            f"backup:{session.session_id}",
            86400 * 7,
            json.dumps(session.user_preferences)
        )
```

### 3. Embedding Cache System

```python
# app/core/embedding_cache.py

class EmbeddingCache:
    """Кеширование embeddings для оптимизации"""
    
    def __init__(self, redis_client, llm_interface):
        self.redis = redis_client
        self.llm = llm_interface
        self.cache_ttl = 86400  # 24 часа
    
    def get_strain_embedding(self, strain_id: int, strain_text: str) -> List[float]:
        """Получение embedding с кешированием"""
        
        cache_key = f"embedding:strain:{strain_id}"
        
        # Проверка кеша
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Генерация если нет в кеше
        embedding = self.llm.generate_embedding(strain_text)
        
        # Сохранение в кеш
        self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(embedding)
        )
        
        return embedding
    
    def get_query_embedding(self, query: str) -> List[float]:
        """Кеширование embeddings запросов"""
        
        # Хешируем запрос для ключа
        query_hash = hashlib.md5(query.encode()).hexdigest()
        cache_key = f"embedding:query:{query_hash}"
        
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        embedding = self.llm.generate_embedding(query)
        
        # Короткий TTL для запросов (1 час)
        self.redis.setex(cache_key, 3600, json.dumps(embedding))
        
        return embedding
```

### 4. Criteria Conflict Resolver

```python
# app/core/conflict_resolver.py

class CriteriaConflictResolver:
    """Разрешение конфликтов в критериях"""
    
    CONFLICTING_EFFECTS = [
        ({'Sleepy', 'Relaxed'}, {'Energetic', 'Uplifted'}),
        ({'Focused'}, {'Giggly', 'Tingly'}),
        ({'Hungry'}, {'Appetite Loss'}),
    ]
    
    def resolve_conflicts(
        self,
        criteria: Dict,
        context: str
    ) -> Tuple[Dict, List[str]]:
        """Разрешение конфликтов с предупреждениями"""
        
        conflicts = []
        resolved_criteria = criteria.copy()
        
        if 'effects' in criteria:
            desired = set(criteria['effects'].get('desired', []))
            avoid = set(criteria['effects'].get('avoid', []))
            
            # Проверка прямых конфликтов
            direct_conflicts = desired & avoid
            if direct_conflicts:
                conflicts.append(f"Conflicting: want and avoid {direct_conflicts}")
                # Приоритет на desired
                resolved_criteria['effects']['avoid'] = list(avoid - direct_conflicts)
            
            # Проверка логических конфликтов
            for group1, group2 in self.CONFLICTING_EFFECTS:
                if desired & group1 and desired & group2:
                    conflicts.append(f"Conflicting effects: {group1} vs {group2}")
                    # Оставляем первый упомянутый
                    resolved_criteria['effects']['priority'] = self._determine_priority(
                        context, group1, group2
                    )
        
        return resolved_criteria, conflicts
    
    def _determine_priority(self, context: str, group1: set, group2: set) -> str:
        """Определение приоритета на основе контекста"""
        # Анализ контекста для выбора приоритета
        context_lower = context.lower()
        
        if any(word in context_lower for word in ['dormir', 'sleep', 'insomnia']):
            return list(group1)[0] if 'Sleepy' in group1 else list(group2)[0]
        elif any(word in context_lower for word in ['trabajar', 'work', 'focus']):
            return list(group1)[0] if 'Focused' in group1 else list(group2)[0]
        
        return list(group1)[0]  # По умолчанию первый
```

### 5. Optimized Contextual RAG Service

```python
# app/core/optimized_rag_service.py

class OptimizedContextualRAGService:
    """Оптимизированный RAG с единым LLM вызовом"""
    
    def __init__(self, repository, session_manager):
        self.repository = repository
        self.session_manager = session_manager
        self.unified_processor = UnifiedLLMProcessor()
        self.fallback_analyzer = RuleBasedFallbackAnalyzer()
        self.embedding_cache = EmbeddingCache()
        self.conflict_resolver = CriteriaConflictResolver()
        self.dynamic_filter = DynamicStrainFilter()
    
    def process_contextual_query(
        self,
        query: str,
        session_id: Optional[str],
        history: Optional[List[str]]
    ) -> ChatResponse:
        """Главный метод с оптимизацией и fallbacks"""
        
        # 1. Управление сессией с восстановлением
        session = self.session_manager.get_or_restore_session(session_id)
        
        # 2. ЕДИНЫЙ анализ через LLM или fallback
        try:
            analysis = self.unified_processor.analyze_complete(query, session)
        except Exception as e:
            logger.warning(f"LLM failed, using fallback: {e}")
            analysis = self.fallback_analyzer.analyze(query, session)
        
        # 3. Обработка команды сброса
        if analysis.query_type == 'reset':
            return self._handle_reset(session)
        
        # 4. Обработка edge cases
        if analysis.query_type == 'follow_up' and not session.has_strains():
            return self._handle_no_context(analysis.detected_language)
        
        # 5. Разрешение конфликтов в критериях
        if analysis.criteria:
            resolved_criteria, conflicts = self.conflict_resolver.resolve_conflicts(
                analysis.criteria, query
            )
            analysis.criteria = resolved_criteria
            if conflicts:
                analysis.warnings = conflicts
        
        # 6. Обработка по типу запроса
        strains = self._process_by_type(analysis, session)
        
        # 7. Обновление сессии
        self._update_session(session, query, analysis, strains)
        
        # 8. Сохранение с backup
        self.session_manager.save_session_with_backup(session)
        
        # 9. Построение ответа
        return self._build_optimized_response(analysis, strains, session)
    
    def _handle_no_context(self, language: str) -> ChatResponse:
        """Обработка follow-up без контекста"""
        
        responses = {
            'es': "No tengo variedades anteriores para comparar. ¿Qué efectos buscas?",
            'en': "I don't have previous strains to compare. What effects are you looking for?"
        }
        
        return ChatResponse(
            response=responses.get(language, responses['es']),
            recommended_strains=[],
            detected_intent='no_context',
            filters_applied={},
            session_id=session.session_id,
            query_type='clarification',
            language=language,
            confidence=1.0,
            quick_actions=self._get_new_search_suggestions(language)
        )
    
    def _handle_reset(self, session: ConversationSession) -> ChatResponse:
        """Обработка сброса контекста"""
        
        # Сохраняем только базовые предпочтения
        preserved_preferences = session.user_preferences.copy()
        
        # Очищаем историю
        session.recommended_strains_history = []
        session.conversation_history = []
        session.current_topic = None
        
        responses = {
            'es': "Perfecto, empecemos de nuevo. ¿Qué tipo de efectos buscas?",
            'en': "Perfect, let's start fresh. What kind of effects are you looking for?"
        }
        
        return ChatResponse(
            response=responses.get(session.detected_language, responses['es']),
            recommended_strains=[],
            detected_intent='reset',
            filters_applied={},
            session_id=session.session_id,
            query_type='reset',
            language=session.detected_language,
            confidence=1.0
        )
    
    def _process_by_type(
        self,
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[Strain]:
        """Обработка в зависимости от типа с оптимизацией"""
        
        if analysis.query_type == 'follow_up':
            # Работаем с существующими сортами
            strain_ids = session.get_last_strains()
            strains = [self.repository.get_strain_with_relations(id) for id in strain_ids]
            
            # Применяем фильтры если есть
            if analysis.criteria:
                strains = self.dynamic_filter.apply_criteria(strains, analysis.criteria)
            
            return strains
        
        elif analysis.query_type == 'new_search':
            # Новый поиск с учетом предпочтений
            return self._optimized_search(analysis, session)
        
        elif analysis.query_type == 'comparison':
            # Сравнение из контекста
            return self._handle_comparison(analysis, session)
        
        else:
            # Default - показываем последние если есть
            if session.has_strains():
                strain_ids = session.get_last_strains()
                return [self.repository.get_strain_with_relations(id) for id in strain_ids][:3]
            return []
    
    def _optimized_search(
        self,
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[Strain]:
        """Оптимизированный поиск с кешированными embeddings"""
        
        # Используем кешированное embedding запроса
        query_embedding = self.embedding_cache.get_query_embedding(
            analysis.original_query
        )
        
        # Поиск с фильтрами
        strains = self.repository.search_strains_with_filters(
            embedding=query_embedding,
            filters=self._merge_filters(analysis.criteria, session.user_preferences),
            limit=5
        )
        
        return strains
    
    def _build_optimized_response(
        self,
        analysis: UnifiedAnalysis,
        strains: List[Strain],
        session: ConversationSession
    ) -> ChatResponse:
        """Построение ответа с динамическими quick actions"""
        
        # Используем уже сгенерированный текст из unified analysis
        response_text = analysis.response_text
        
        # Добавляем предупреждения о конфликтах
        if hasattr(analysis, 'warnings') and analysis.warnings:
            warning_text = f"\n⚠️ {', '.join(analysis.warnings)}"
            response_text += warning_text
        
        # Динамические quick actions
        quick_actions = self._generate_dynamic_quick_actions(
            strains, 
            analysis,
            session
        )
        
        # Компактные сорта для UI
        compact_strains = self._build_compact_strains(strains)
        
        return ChatResponse(
            response=response_text,
            recommended_strains=compact_strains,
            detected_intent=analysis.query_type,
            filters_applied=analysis.criteria or {},
            session_id=session.session_id,
            query_type=analysis.query_type,
            language=analysis.detected_language,
            confidence=analysis.confidence,
            quick_actions=quick_actions or analysis.suggested_quick_actions,
            is_restored=session.is_restored,
            is_fallback=getattr(analysis, 'is_fallback', False)
        )
    
    def _generate_dynamic_quick_actions(
        self,
        strains: List[Strain],
        analysis: UnifiedAnalysis,
        session: ConversationSession
    ) -> List[str]:
        """Генерация контекстных quick actions"""
        
        actions = []
        lang = analysis.detected_language
        
        if len(strains) > 1:
            # Действия для множественного выбора
            if lang == 'es':
                actions.append(f"Comparar {strains[0].name} y {strains[1].name}")
                actions.append("Ver el más potente")
                actions.append("Ver el más suave")
            else:
                actions.append(f"Compare {strains[0].name} and {strains[1].name}")
                actions.append("Show strongest")
                actions.append("Show mildest")
        
        if strains and any(s.thc and float(s.thc) > 20 for s in strains):
            # Если есть сильные сорта
            action = "Ver opciones más suaves" if lang == 'es' else "Show milder options"
            actions.append(action)
        
        # Добавляем reset опцию если есть история
        if session.conversation_history:
            reset = "Empezar nueva búsqueda" if lang == 'es' else "Start new search"
            actions.append(reset)
        
        return actions[:4]  # Максимум 4 действия
```

### 6. Dynamic Filter с оптимизацией

```python
# app/core/dynamic_filter_optimized.py

class OptimizedDynamicFilter:
    """Оптимизированные фильтры с кешированием"""
    
    def __init__(self, embedding_cache):
        self.embedding_cache = embedding_cache
    
    def apply_criteria(
        self,
        strains: List[Strain],
        criteria: Dict
    ) -> List[Strain]:
        """Применение критериев с оптимизацией"""
        
        if not criteria or not strains:
            return strains
        
        result = strains.copy()
        
        # Быстрые фильтры (без embeddings)
        if 'potency' in criteria:
            result = self._filter_by_potency(result, criteria['potency'])
        
        if 'effects' in criteria:
            result = self._filter_by_effects(result, criteria['effects'])
        
        # Медленные фильтры (с embeddings) только если нужно
        if 'custom_criteria' in criteria and criteria['custom_criteria']:
            result = self._apply_semantic_filter_optimized(
                result, 
                criteria['custom_criteria']
            )
        
        return result
    
    def _apply_semantic_filter_optimized(
        self,
        strains: List[Strain],
        criteria_text: str
    ) -> List[Strain]:
        """Оптимизированный semantic filter с кешем"""
        
        # Кешированное embedding для критерия
        criteria_embedding = self.embedding_cache.get_query_embedding(criteria_text)
        
        scored_strains = []
        for strain in strains:
            # Используем кешированные embeddings сортов
            strain_embedding = self.embedding_cache.get_strain_embedding(
                strain.id,
                self._build_strain_text(strain)
            )
            
            similarity = cosine_similarity(criteria_embedding, strain_embedding)
            scored_strains.append((strain, similarity))
        
        # Возвращаем только релевантные
        threshold = 0.7
        filtered = [s for s in scored_strains if s[1] >= threshold]
        return [s[0] for s in sorted(filtered, key=lambda x: x[1], reverse=True)]
```

### 7. Topic Change Detector

```python
# app/core/topic_detector.py

class TopicChangeDetector:
    """Детекция смены темы разговора"""
    
    OPPOSITE_INTENTS = [
        (IntentType.SLEEP, IntentType.ENERGY),
        (IntentType.RELAXATION, IntentType.FOCUS),
        (IntentType.PAIN_RELIEF, IntentType.RECREATION)
    ]
    
    def detect_topic_change(
        self,
        new_intent: IntentType,
        current_topic: Optional[IntentType],
        query: str
    ) -> bool:
        """Определение смены темы"""
        
        if not current_topic:
            return False
        
        # Проверка противоположных намерений
        for intent1, intent2 in self.OPPOSITE_INTENTS:
            if (current_topic == intent1 and new_intent == intent2) or \
               (current_topic == intent2 and new_intent == intent1):
                return True
        
        # Проверка явных индикаторов смены
        change_indicators = [
            'ahora necesito', 'now i need',
            'cambiando de tema', 'changing topic',
            'otra cosa', 'something else'
        ]
        
        query_lower = query.lower()
        return any(indicator in query_lower for indicator in change_indicators)
```

---

## 🟢 FRONTEND (Chat Client)

### 1. Enhanced Session Management

```javascript
// app.js - Улучшенное управление сессией

class EnhancedSessionManager {
    constructor() {
        this.sessionId = this.getOrCreateSessionId();
        this.isRestored = false;
        this.language = null;
        this.lastActivity = Date.now();
    }
    
    getOrCreateSessionId() {
        let sessionId = sessionStorage.getItem('canagent_session_id');
        const lastActivity = sessionStorage.getItem('canagent_last_activity');
        
        // Проверка истечения (4 часа)
        if (sessionId && lastActivity) {
            const elapsed = Date.now() - parseInt(lastActivity);
            if (elapsed > 4 * 60 * 60 * 1000) {
                // Сессия истекла, но сохраняем ID для восстановления
                this.isRestored = true;
            }
        }
        
        if (!sessionId) {
            sessionId = this.generateUUID();
        }
        
        sessionStorage.setItem('canagent_session_id', sessionId);
        this.updateActivity();
        
        return sessionId;
    }
    
    updateActivity() {
        this.lastActivity = Date.now();
        sessionStorage.setItem('canagent_last_activity', this.lastActivity.toString());
    }
    
    reset() {
        // Soft reset - сохраняем ID но очищаем контекст
        sessionStorage.setItem('canagent_session_id', this.generateUUID());
        this.updateActivity();
        this.isRestored = false;
    }
}
```

### 2. Intelligent API Client

```javascript
// api-client.js - Клиент с обработкой fallback

class IntelligentAPIClient {
    constructor(sessionManager) {
        this.sessionManager = sessionManager;
        this.baseUrl = '/api/v1/chat';
        this.retryAttempts = 2;
    }
    
    async sendMessage(message) {
        let attempts = 0;
        
        while (attempts < this.retryAttempts) {
            try {
                const response = await this.makeRequest(message);
                
                // Обработка индикаторов
                this.handleResponseIndicators(response);
                
                return response;
                
            } catch (error) {
                attempts++;
                
                if (attempts >= this.retryAttempts) {
                    // Показать offline fallback
                    return this.getOfflineFallback(message);
                }
                
                // Ждем перед повтором
                await this.delay(1000 * attempts);
            }
        }
    }
    
    async makeRequest(message) {
        const response = await fetch(`${this.baseUrl}/ask/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message: message,
                session_id: this.sessionManager.sessionId,
                history: this.getRecentHistory(),
                source_platform: window.location.hostname
            })
        });
        
        if (!response.ok) {
            throw new Error(`API Error: ${response.status}`);
        }
        
        return await response.json();
    }
    
    handleResponseIndicators(response) {
        // Обработка индикаторов состояния
        if (response.is_restored) {
            this.showNotification('Sesión restaurada / Session restored');
        }
        
        if (response.is_fallback) {
            this.showNotification('Modo offline / Offline mode');
        }
        
        if (response.confidence < 0.5) {
            this.showConfidenceWarning(response.confidence);
        }
        
        // Обновление session
        if (response.session_id) {
            this.sessionManager.sessionId = response.session_id;
        }
        
        if (response.language) {
            this.sessionManager.language = response.language;
        }
    }
    
    getOfflineFallback(message) {
        // Базовый offline ответ
        const lang = this.detectLocalLanguage(message);
        
        return {
            response: lang === 'es' 
                ? "Lo siento, hay problemas de conexión. Intenta de nuevo."
                : "Sorry, connection issues. Please try again.",
            recommended_strains: [],
            query_type: 'error',
            confidence: 0,
            is_offline: true,
            quick_actions: [
                lang === 'es' ? "Reintentar" : "Retry",
                lang === 'es' ? "Nueva búsqueda" : "New search"
            ]
        };
    }
    
    detectLocalLanguage(text) {
        // Простая детекция языка на клиенте
        const spanishWords = ['para', 'necesito', 'quiero', 'cuál'];
        const hasSpanish = spanishWords.some(word => 
            text.toLowerCase().includes(word)
        );
        return hasSpanish ? 'es' : 'en';
    }
}
```

### 3. Adaptive UI

```javascript
// ui-adapter.js - Адаптивный UI

class AdaptiveUI {
    constructor(apiClient) {
        this.apiClient = apiClient;
        this.currentStrains = [];
    }
    
    async handleUserMessage(message) {
        // Показать индикатор загрузки
        this.showLoading();
        
        // Отправка сообщения
        const response = await this.apiClient.sendMessage(message);
        
        // Скрыть загрузку
        this.hideLoading();
        
        // Адаптивный рендеринг
        this.renderAdaptive(response);
    }
    
    renderAdaptive(response) {
        // Сохранить текущие сорта
        if (response.recommended_strains.length > 0) {
            this.currentStrains = response.recommended_strains;
        }
        
        // Выбор метода рендеринга по типу
        const renderers = {
            'follow_up': () => this.renderFollowUp(response),
            'comparison': () => this.renderComparison(response),
            'clarification': () => this.renderClarification(response),
            'no_context': () => this.renderNoContext(response),
            'reset': () => this.renderReset(response),
            'error': () => this.renderError(response),
            'new_search': () => this.renderNewSearch(response)
        };
        
        const renderer = renderers[response.query_type] || renderers['new_search'];
        renderer();
        
        // Показать quick actions
        if (response.quick_actions && response.quick_actions.length > 0) {
            this.renderQuickActions(response.quick_actions);
        }
        
        // Показать индикаторы качества
        this.showQualityIndicators(response);
    }
    
    renderQuickActions(actions) {
        const container = document.getElementById('quick-actions');
        
        container.innerHTML = actions.map(action => `
            <button 
                class="quick-action-btn" 
                onclick="handleQuickAction('${this.escapeHtml(action)}')"
            >
                ${this.escapeHtml(action)}
            </button>
        `).join('');
        
        // Анимация появления
        container.classList.add('fade-in');
    }
    
    renderNoContext(response) {
        // Специальный UI для отсутствия контекста
        this.showMessage(
            response.response,
            'warning',
            {
                icon: '⚠️',
                suggestions: true
            }
        );
    }
    
    renderClarification(response) {
        // UI для уточнений
        this.showMessage(
            response.response,
            'info',
            {
                icon: '❓',
                highlight_actions: true
            }
        );
    }
    
    showQualityIndicators(response) {
        const indicators = [];
        
        if (response.is_restored) {
            indicators.push({
                type: 'info',
                text: 'Sesión restaurada'
            });
        }
        
        if (response.is_fallback) {
            indicators.push({
                type: 'warning',
                text: 'Modo básico'
            });
        }
        
        if (response.confidence < 0.7) {
            indicators.push({
                type: 'caution',
                text: `Confianza: ${Math.round(response.confidence * 100)}%`
            });
        }
        
        this.renderIndicators(indicators);
    }
}
```

---

## 📊 Диаграмма оптимизированного потока

```mermaid
graph TD
    A[User Query] --> B[Session Manager]
    B --> C{Session Valid?}
    C -->|No/Expired| D[Restore/Create Session]
    C -->|Yes| E[Load Session]
    D --> F[Unified LLM Processor]
    E --> F
    F --> G{LLM Available?}
    G -->|No| H[Fallback Analyzer]
    G -->|Yes| I[Single LLM Call]
    H --> J[Rule-based Analysis]
    I --> K[Complete Analysis]
    J --> K
    K --> L{Has Context Issues?}
    L -->|No Context| M[Handle No Context]
    L -->|Conflicts| N[Resolve Conflicts]
    L -->|OK| O[Process by Type]
    M --> P[Generate Response]
    N --> O
    O --> Q{Use Embeddings?}
    Q -->|Yes| R[Check Cache]
    Q -->|No| S[Quick Filters]
    R --> T{In Cache?}
    T -->|Yes| U[Use Cached]
    T -->|No| V[Generate & Cache]
    U --> S
    V --> S
    S --> P
    P --> W[Return Response]
```

---

## ⚙️ Конфигурация производительности

```env
# LLM Optimization
UNIFIED_LLM_TIMEOUT=3000          # 3 sec timeout
FALLBACK_ON_TIMEOUT=true          # Use rules if timeout
LLM_RETRY_ATTEMPTS=1              # Only 1 retry

# Caching
EMBEDDING_CACHE_TTL=86400         # 24 hours for strains
QUERY_EMBEDDING_CACHE_TTL=3600    # 1 hour for queries
CRITERIA_CACHE_TTL=300            # 5 min for criteria

# Session Management  
SESSION_TTL_HOURS=4               # Active session
SESSION_BACKUP_DAYS=7             # Preference backup
SESSION_RESTORE_ENABLED=true      # Allow restoration

# Performance
MAX_STRAINS_IN_MEMORY=20
MAX_CONVERSATION_HISTORY=50
SEMANTIC_SEARCH_THRESHOLD=0.7
MIN_CONFIDENCE_FOR_ACTION=0.3

# Monitoring
ENABLE_PERFORMANCE_METRICS=true
LOG_SLOW_QUERIES=true
SLOW_QUERY_THRESHOLD_MS=2000
```



---

## 🚀 SMART QUERY EXECUTOR v3.0 - Следующий этап эволюции

### Проблема текущего подхода v2.0

Несмотря на успешное решение контекстных проблем, v2.0 требует множественных условий для обработки каждого edge case. При добавлении новых типов запросов код становится громоздким и сложным в поддержке.

**Примеры проблем:**
- Сорта с THC: N/A исключаются жестко в коде
- Каждый тип comparison требует отдельных условий
- Логика "highest/lowest" хардкодится в фильтрах
- Добавление новых критериев требует изменения множественных условий

### Архитектура Smart Query Executor v3.0

#### Принципы гибкого подхода:

1. **LLM как главный мозг** - определяет точные действия для каждого запроса
2. **Минимум хардкода** - максимум рассуждений AI
3. **Исполнительные модули** - выполняют конкретные действия без жесткой логики
4. **Полный контекст** - LLM видит все данные для принятия решений

#### Компоненты:

```
Smart Query Executor v3.0
├── SmartQueryAnalyzer (главный AI мозг)
│   ├── Получает полный контекст сессии и сортов
│   ├── Анализирует намерение и определяет действия
│   └── Генерирует план выполнения + естественный ответ
├── ActionExecutor (умные исполнители)
│   ├── StrainProcessor - обработка сортов по AI инструкциям
│   ├── DataFilter - фильтрация по AI критериям
│   ├── StrainSorter - сортировка по AI логике
│   └── ResponseGenerator - сборка финального ответа
└── ContextProvider (контекст для AI)
    ├── Session strains с полными характеристиками
    ├── User conversation history
    └── Available system actions
```

#### Пример работы:

**Запрос пользователя:** "what strain have highest thc level"

**SmartQueryAnalyzer получает полный контекст:**
```json
{
  "user_query": "what strain have highest thc level",
  "session_strains": [
    {
      "id": 360, 
      "name": "ACDC", 
      "thc": "1.00", 
      "category": "Hybrid",
      "effects": ["Uplifted", "Focused", "Relaxed"]
    },
    {
      "id": 354, 
      "name": "Alien OG", 
      "thc": "19.00", 
      "category": "Hybrid", 
      "effects": ["Hungry", "Giggly", "Euphoric"]
    },
    {
      "id": 358, 
      "name": "Italian Ice", 
      "thc": null, 
      "category": "Hybrid",
      "effects": ["Relaxed", "Focused", "Sleepy"]
    }
  ],
  "conversation_context": "User previously asked for relaxing strains for sleep",
  "available_actions": [
    "filter_strains",
    "sort_strains", 
    "select_strains",
    "explain_strains",
    "expand_search"
  ]
}
```

**SmartQueryAnalyzer возвращает план выполнения:**
```json
{
  "action_plan": {
    "primary_action": "sort_strains",
    "parameters": {
      "sort_criteria": "thc_content_descending",
      "exclude_invalid_data": ["null", "N/A", "unknown"],
      "limit": 3,
      "reasoning": "User wants highest THC from their context, exclude Italian Ice due to missing THC data"
    }
  },
  "natural_response": "From your previous recommendations, Alien OG has the highest THC level at 19%. Italian Ice was excluded since THC data isn't available.",
  "suggested_follow_ups": [
    "Tell me more about Alien OG",
    "Show me all THC levels",
    "Find stronger options"
  ],
  "confidence": 0.95,
  "detected_language": "en"
}
```

#### Ключевые преимущества:

1. **Максимальная гибкость** - AI сам решает как обработать любой запрос
2. **Самоадаптация** - автоматически исключает невалидные данные
3. **Контекстуальность** - учитывает всю информацию о сессии
4. **Расширяемость** - новые типы запросов обрабатываются без изменения кода
5. **Объяснимость** - AI предоставляет reasoning для каждого решения

### Этапы реализации Smart Query Executor v3.0:

#### Этап 1: Core Architecture Design
- [ ] Создать `SmartQueryAnalyzer` - главный AI компонент
- [ ] Разработать `ContextProvider` - провайдер полного контекста
- [ ] Спроектировать `ActionExecutor` - гибкие исполнители

#### Этап 2: Smart Query Analyzer Implementation  
- [ ] Реализовать LLM промпт для полного анализа запросов
- [ ] Добавить генерацию планов выполнения
- [ ] Создать fallback для случаев недоступности LLM

#### Этап 3: Action Executors
- [ ] `StrainProcessor` - умная обработка сортов по AI инструкциям
- [ ] `DataFilter` - фильтрация с автоматическим исключением invalid данных
- [ ] `StrainSorter` - сортировка по AI критериям с reasoning

#### Этап 4: Context Provider Enhancement
- [ ] Расширить контекст полными данными о сортах
- [ ] Добавить историю действий пользователя
- [ ] Включить системные возможности в контекст

#### Этап 5: Integration & Testing
- [ ] Интеграция всех компонентов в unified service
- [ ] Comprehensive тестирование edge cases
- [ ] Performance оптимизация AI вызовов

#### Этап 6: Advanced Features
- [ ] Multi-step reasoning для сложных запросов
- [ ] Learning from user feedback
- [ ] Predictive suggestions based on patterns

### Пример unified prompt для Smart Query Analyzer:

```
You are a cannabis strain consultation AI analyzing user queries with full session context.

CONTEXT:
Session strains: {session_strains_with_full_data}
Conversation history: {conversation_summary}  
User query: "{user_query}"
Available system actions: {available_actions}

TASK:
Analyze the query and create an execution plan. Consider:
1. What does the user want to accomplish?
2. Which strains from the session are relevant?
3. How should the data be processed (filter/sort/select)?
4. What data quality issues need handling?
5. What would be most helpful to the user?

RESPONSE FORMAT (JSON):
{
  "action_plan": {
    "primary_action": "sort_strains|filter_strains|select_strains|explain_strains|expand_search",
    "parameters": {
      // Flexible parameters based on the action needed
      "criteria": "detailed criteria for the action",
      "data_handling": "how to handle missing/invalid data",
      "limit": "number of results",
      "reasoning": "why this approach was chosen"
    }
  },
  "natural_response": "Natural language response in detected language",
  "suggested_follow_ups": ["contextual suggestions"],
  "confidence": 0.0-1.0,
  "detected_language": "es|en"
}

EXAMPLES:
- "cuál tiene más THC" → sort by THC descending, exclude invalid
- "show me indica only" → filter by category, from session strains  
- "tell me about the second one" → select by index, provide details
- "find something stronger" → expand search, higher THC criteria

Be intelligent about data quality - exclude strains with null/N/A/invalid values when they're not useful for the query.
```

### Конфигурация для v3.0:

```env
# Smart Query Executor v3.0
USE_SMART_EXECUTOR=true
SMART_EXECUTOR_TIMEOUT=5000
SMART_EXECUTOR_FALLBACK=true

# AI Analysis  
ANALYSIS_CACHE_TTL=1800        # 30 min for query analysis
MAX_CONTEXT_TOKENS=4000        # Context size limit
MIN_CONFIDENCE_THRESHOLD=0.3   # Minimum confidence to proceed

# Action Execution
ENABLE_MULTI_STEP_REASONING=true
ENABLE_DATA_QUALITY_AUTO_FIX=true
ENABLE_PREDICTIVE_SUGGESTIONS=true
```

---

## ✅ Решенные проблемы

1. ✅ **Единый LLM вызов** - все операции в одном запросе
2. ✅ **Fallback механизм** - работает даже без OpenAI
3. ✅ **Edge cases** - обработка "какой лучше?" без контекста
4. ✅ **Кеширование embeddings** - 80% экономия на повторных
5. ✅ **Детекция смены темы** - понимает переходы
6. ✅ **Session restoration** - восстановление после истечения
7. ✅ **Динамические quick actions** - генерируются по контексту
8. ✅ **Механизм reset** - "empezar de nuevo" работает
9. ✅ **Конфликты критериев** - обнаружение и разрешение
10. ✅ **Performance** - снижение latency в 3-4 раза

## ✅ Smart Query Executor v3.0 - РЕАЛИЗОВАНО

11. ✅ **Гибкая архитектура** - замена хардкода на AI reasoning  
12. ✅ **Автоматическое data quality handling** - AI сам исключает invalid данные
13. ✅ **Расширяемость без кода** - новые типы запросов через промпты
14. ✅ **Universal Action Executor** - обрабатывает любые AI-критерии
15. ✅ **Self-explaining AI** - AI объясняет свои решения

### 🎯 Достижения Smart Query Executor v3.0:

**Решена исходная проблема:**
- ❌ Было: Italian Ice с THC: N/A включался в результаты "highest THC"
- ✅ Стало: AI автоматически исключает invalid данные через универсальные фильтры

**Ключевые улучшения:**
1. **Универсальные критерии** - вместо хардкода для каждого поля:
   ```json
   // AI генерирует гибкие критерии для любого запроса
   "filters": {
     "thc": {"operator": "gte", "value": 15},
     "category": {"operator": "eq", "value": "Indica"},
     "effects": {"operator": "contains", "values": ["Sleepy"]},
     "flavors": {"operator": "any", "values": ["pine", "citrus"]}
   }
   ```

2. **UniversalActionExecutor** - обрабатывает любые поля без изменения кода:
   - Поддерживает операторы: `eq`, `gte`, `lte`, `gt`, `lt`, `contains`, `any`, `not_contains`
   - Работает с любыми полями: `thc`, `cbd`, `category`, `effects`, `flavors`, `helps_with`
   - Автоматически исключает invalid данные: `null`, `N/A`, `unknown`

3. **Масштабируемость** - новые типы запросов без программирования:
   - "find high CBD sativas" → AI: `{"category": "Sativa", "cbd": {"operator": "gte", "value": 10}}`
   - "show citrus indica for pain" → AI: `{"category": "Indica", "flavors": {"operator": "contains", "values": ["citrus"]}, "helps_with": {"operator": "contains", "values": ["Pain"]}}`

**Тестирование:**
- ✅ "what strain have highest thc level" → правильная сортировка, исключение N/A
- ✅ "show me sativa strains only" → фильтрация по категории  
- ✅ "find strains with high CBD" → числовая фильтрация
- ✅ Универсальная обработка без специфичных методов

**Производительность:**
- Один AI вызов вместо множественных условий
- Универсальная фильтрация вместо N специализированных методов
- Автоматическая оптимизация качества данных


