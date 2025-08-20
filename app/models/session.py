from datetime import datetime
from typing import List, Optional, Dict, Set, Any
from pydantic import BaseModel, Field
from app.core.intent_detection import IntentType
import uuid
import json


class ConversationSession(BaseModel):
    """Enhanced session model с восстановлением контекста"""
    
    session_id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(default_factory=datetime.now, description="Session creation time")
    last_activity: datetime = Field(default_factory=datetime.now, description="Last activity timestamp")
    detected_language: Optional[str] = Field(default=None, description="Detected user language (es/en)")
    is_restored: bool = Field(default=False, description="Flag for restored session")
    
    # История с ограничением (максимум 20 групп рекомендаций)
    recommended_strains_history: List[List[int]] = Field(
        default_factory=list, 
        description="History of recommended strain IDs (max 20)"
    )
    current_topic: Optional[IntentType] = Field(default=None, description="Current conversation topic")
    previous_topics: List[IntentType] = Field(default_factory=list, description="Previous topics in session")
    
    # Накопленные предпочтения пользователя
    user_preferences: Dict[str, Set[str]] = Field(
        default_factory=dict,
        description="Accumulated user preferences"
    )
    
    # Детальная история разговора (максимум 50 сообщений)
    conversation_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed conversation history (max 50)"
    )
    
    class Config:
        # Для корректной сериализации Set и IntentType
        json_encoders = {
            set: list,
            IntentType: lambda v: v.value if v else None
        }
    
    def has_strains(self) -> bool:
        """Проверка наличия рекомендованных сортов"""
        return bool(self.recommended_strains_history)
    
    def get_last_strains(self) -> List[int]:
        """Безопасное получение последних сортов"""
        if self.recommended_strains_history:
            return self.recommended_strains_history[-1]
        return []
    
    def add_strain_recommendation(self, strain_ids: List[int]):
        """Добавить новую группу рекомендованных сортов"""
        if strain_ids:
            self.recommended_strains_history.append(strain_ids)
            # Ограничиваем историю максимум 20 группами
            if len(self.recommended_strains_history) > 20:
                self.recommended_strains_history = self.recommended_strains_history[-20:]
    
    def add_conversation_entry(self, query: str, response: str, intent: Optional[IntentType] = None):
        """Добавить запись в историю разговора"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "response": response,
            "intent": intent.value if intent else None
        }
        self.conversation_history.append(entry)
        # Ограничиваем историю максимум 50 записями
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]
    
    def update_topic(self, new_topic: IntentType):
        """Обновить текущую тему разговора"""
        if self.current_topic and self.current_topic != new_topic:
            self.previous_topics.append(self.current_topic)
            # Ограничиваем историю тем
            if len(self.previous_topics) > 10:
                self.previous_topics = self.previous_topics[-10:]
        self.current_topic = new_topic
    
    def update_preferences(self, category: str, values: List[str]):
        """Обновить пользовательские предпочтения"""
        if category not in self.user_preferences:
            self.user_preferences[category] = set()
        self.user_preferences[category].update(values)
    
    def update_activity(self):
        """Обновить время последней активности"""
        self.last_activity = datetime.now()
    
    def to_json(self) -> str:
        """Сериализация в JSON для Redis"""
        # Конвертируем Set в list и IntentType в строку для JSON
        data = self.dict()
        
        # Обработка user_preferences (Set -> List)
        if data.get('user_preferences'):
            data['user_preferences'] = {
                k: list(v) if isinstance(v, set) else v 
                for k, v in data['user_preferences'].items()
            }
        
        # Обработка IntentType
        if data.get('current_topic'):
            data['current_topic'] = data['current_topic'].value if hasattr(data['current_topic'], 'value') else data['current_topic']
        
        if data.get('previous_topics'):
            data['previous_topics'] = [
                topic.value if hasattr(topic, 'value') else topic 
                for topic in data['previous_topics']
            ]
        
        return json.dumps(data, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ConversationSession':
        """Десериализация из JSON"""
        data = json.loads(json_str)
        
        # Восстановление Set из list
        if data.get('user_preferences'):
            data['user_preferences'] = {
                k: set(v) if isinstance(v, list) else v 
                for k, v in data['user_preferences'].items()
            }
        
        # Восстановление IntentType из строки
        if data.get('current_topic'):
            try:
                data['current_topic'] = IntentType(data['current_topic'])
            except (ValueError, TypeError):
                data['current_topic'] = None
        
        if data.get('previous_topics'):
            restored_topics = []
            for topic in data['previous_topics']:
                try:
                    restored_topics.append(IntentType(topic))
                except (ValueError, TypeError):
                    continue
            data['previous_topics'] = restored_topics
        
        # Восстановление datetime из строки
        for field in ['created_at', 'last_activity']:
            if data.get(field) and isinstance(data[field], str):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except ValueError:
                    data[field] = datetime.now()
        
        return cls(**data)
    
    @classmethod
    def create_new(cls) -> 'ConversationSession':
        """Создать новую сессию"""
        return cls(
            session_id=str(uuid.uuid4()),
            created_at=datetime.now(),
            last_activity=datetime.now()
        )


class UnifiedAnalysis(BaseModel):
    """Результат единого анализа LLM"""
    
    detected_language: str = Field(..., description="Detected language (es/en)")
    query_type: str = Field(..., description="Query type: new_search|follow_up|comparison|detail_request|reset|clarification")
    confidence: float = Field(..., description="Analysis confidence (0.0-1.0)")
    topic_changed: bool = Field(default=False, description="Whether topic changed")
    
    criteria: Optional[Dict[str, Any]] = Field(default=None, description="Extracted search criteria")
    action_needed: str = Field(..., description="Required action: filter|sort|compare|select|explain|clarify")
    suggested_quick_actions: List[str] = Field(default_factory=list, description="Dynamic suggestions")
    response_text: str = Field(..., description="Generated response text")
    
    # Дополнительные поля для fallback режима
    is_fallback: bool = Field(default=False, description="Whether this is fallback analysis")
    original_query: str = Field(default="", description="Original user query")
    warnings: List[str] = Field(default_factory=list, description="Conflict warnings")