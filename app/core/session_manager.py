import json
import uuid
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.models.session import ConversationSession
from app.core.cache import get_redis

logger = logging.getLogger(__name__)


class ImprovedSessionManager:
    """Менеджер сессий с graceful восстановлением"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis()
        self.session_ttl = 3600 * 4  # 4 часа активная сессия
        self.backup_ttl = 86400 * 7  # 7 дней для backup предпочтений
        
    def get_or_restore_session(self, session_id: Optional[str]) -> ConversationSession:
        """Получение или восстановление сессии с graceful fallback"""
        
        if not session_id:
            logger.info("No session_id provided, creating new session")
            return self.create_new_session()
        
        # Попытка получить активную сессию
        session = self.get_active_session(session_id)
        
        if session:
            logger.info(f"Retrieved active session: {session_id}")
            return session
        
        # Попытка восстановления истекшей сессии
        logger.info(f"Session {session_id} not active, attempting restoration")
        session = self.restore_expired_session(session_id)
        
        return session
    
    def get_active_session(self, session_id: str) -> Optional[ConversationSession]:
        """Получение активной сессии из Redis"""
        
        try:
            session_key = f"session:{session_id}"
            session_data = self.redis.get(session_key)
            
            if session_data:
                session = ConversationSession.from_json(session_data)
                # Обновляем время последней активности
                session.update_activity()
                return session
            
        except Exception as e:
            logger.error(f"Error retrieving session {session_id}: {e}")
        
        return None
    
    def restore_expired_session(self, session_id: str) -> ConversationSession:
        """Восстановление истекшей сессии с базовым контекстом"""
        
        session = ConversationSession(
            session_id=session_id,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            is_restored=True
        )
        
        # Попытка восстановить предпочтения из backup
        try:
            backup_key = f"backup:{session_id}"
            backup_data = self.redis.get(backup_key)
            
            if backup_data:
                preferences = json.loads(backup_data)
                # Конвертируем обратно в Set
                session.user_preferences = {
                    k: set(v) if isinstance(v, list) else v 
                    for k, v in preferences.items()
                }
                logger.info(f"Restored preferences for session {session_id}")
            else:
                logger.info(f"No backup preferences found for session {session_id}")
                
        except Exception as e:
            logger.error(f"Error restoring preferences for {session_id}: {e}")
        
        return session
    
    def create_new_session(self) -> ConversationSession:
        """Создание новой сессии"""
        
        session = ConversationSession.create_new()
        logger.info(f"Created new session: {session.session_id}")
        
        return session
    
    def save_session_with_backup(self, session: ConversationSession):
        """Сохранение сессии с backup для восстановления"""
        
        try:
            # Обновляем время активности перед сохранением
            session.update_activity()
            
            # Основное сохранение в Redis
            session_key = f"session:{session.session_id}"
            self.redis.setex(
                session_key,
                self.session_ttl,
                session.to_json()
            )
            
            # Backup ключевых предпочтений (на 7 дней)
            if session.user_preferences:
                backup_key = f"backup:{session.session_id}"
                # Конвертируем Set в list для JSON
                preferences_backup = {
                    k: list(v) if isinstance(v, set) else v 
                    for k, v in session.user_preferences.items()
                }
                
                self.redis.setex(
                    backup_key,
                    self.backup_ttl,
                    json.dumps(preferences_backup)
                )
            
            logger.info(f"Session saved: {session.session_id}")
            
        except Exception as e:
            logger.error(f"Error saving session {session.session_id}: {e}")
            raise
    
    def delete_session(self, session_id: str):
        """Удаление сессии и её backup"""
        
        try:
            session_key = f"session:{session_id}"
            backup_key = f"backup:{session_id}"
            
            # Удаляем основную сессию и backup
            pipeline = self.redis.pipeline()
            pipeline.delete(session_key)
            pipeline.delete(backup_key)
            pipeline.execute()
            
            logger.info(f"Session deleted: {session_id}")
            
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
    
    def extend_session_ttl(self, session_id: str):
        """Продление TTL активной сессии"""
        
        try:
            session_key = f"session:{session_id}"
            self.redis.expire(session_key, self.session_ttl)
            logger.debug(f"Extended TTL for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Error extending TTL for {session_id}: {e}")
    
    def get_session_stats(self) -> dict:
        """Получение статистики сессий для мониторинга"""
        
        try:
            # Подсчет активных сессий
            active_sessions = len(self.redis.keys("session:*"))
            backup_sessions = len(self.redis.keys("backup:*"))
            
            return {
                "active_sessions": active_sessions,
                "backup_sessions": backup_sessions,
                "session_ttl_hours": self.session_ttl / 3600,
                "backup_ttl_days": self.backup_ttl / 86400
            }
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {
                "active_sessions": -1,
                "backup_sessions": -1,
                "error": str(e)
            }
    
    def cleanup_expired_backups(self):
        """Cleanup устаревших backup записей (maintenance задача)"""
        
        try:
            # Redis автоматически удаляет записи с истекшим TTL
            # Эта функция может быть расширена для дополнительной очистки
            
            backup_keys = self.redis.keys("backup:*")
            logger.info(f"Found {len(backup_keys)} backup sessions")
            
            # Здесь можно добавить дополнительную логику очистки
            # если понадобится более сложное управление TTL
            
        except Exception as e:
            logger.error(f"Error during backup cleanup: {e}")


# Глобальный экземпляр менеджера сессий
_session_manager = None

def get_session_manager() -> ImprovedSessionManager:
    """Получить глобальный экземпляр session manager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = ImprovedSessionManager()
    return _session_manager