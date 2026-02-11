import json
import logging
import uuid
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from app.models.session import ConversationSession
from app.core.cache import get_redis, get_async_redis

logger = logging.getLogger(__name__)


class SessionLockTimeout(Exception):
    """Raised when the distributed session lock cannot be acquired in time."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Could not acquire session lock for {session_id} within timeout")


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
    
    # ---------- Distributed locks for session race condition protection ----------

    @contextmanager
    def session_lock(self, session_id: Optional[str]):
        """Sync distributed lock for session read-modify-write protection.

        Raises ``SessionLockTimeout`` if the lock cannot be acquired within
        ``blocking_timeout`` seconds, guaranteeing serialized access.
        """
        if not session_id:
            yield
            return

        lock = self.redis.lock(
            f"lock:session:{session_id}",
            timeout=30,
            blocking_timeout=10,
        )
        acquired = lock.acquire(blocking=True)
        if not acquired:
            logger.error(f"Session lock timeout for {session_id}")
            raise SessionLockTimeout(session_id)
        try:
            yield
        finally:
            try:
                lock.release()
            except Exception as e:
                logger.warning(f"Error releasing session lock for {session_id}: {e}")

    @asynccontextmanager
    async def async_session_lock(self, session_id: Optional[str]):
        """Async distributed lock for session read-modify-write protection.

        Raises ``SessionLockTimeout`` if the lock cannot be acquired within
        ``blocking_timeout`` seconds, guaranteeing serialized access.
        """
        if not session_id:
            yield
            return

        r = await get_async_redis()
        lock = r.lock(
            f"lock:session:{session_id}",
            timeout=30,
            blocking_timeout=10,
        )
        acquired = await lock.acquire(blocking=True)
        if not acquired:
            logger.error(f"Async session lock timeout for {session_id}")
            raise SessionLockTimeout(session_id)
        try:
            yield
        finally:
            try:
                await lock.release()
            except Exception as e:
                logger.warning(f"Error releasing async session lock for {session_id}: {e}")

    # ---------- Async methods (use redis.asyncio) ----------

    async def aget_or_restore_session(self, session_id: Optional[str]) -> ConversationSession:
        """Async version of get_or_restore_session"""
        if not session_id:
            logger.info("No session_id provided, creating new session")
            return self.create_new_session()

        session = await self.aget_active_session(session_id)
        if session:
            logger.info(f"Retrieved active session (async): {session_id}")
            return session

        logger.info(f"Session {session_id} not active, attempting async restoration")
        return await self.arestore_expired_session(session_id)

    async def aget_active_session(self, session_id: str) -> Optional[ConversationSession]:
        """Async version of get_active_session"""
        try:
            r = await get_async_redis()
            session_data = await r.get(f"session:{session_id}")
            if session_data:
                session = ConversationSession.from_json(session_data)
                session.update_activity()
                return session
        except Exception as e:
            logger.error(f"Async error retrieving session {session_id}: {e}")
        return None

    async def arestore_expired_session(self, session_id: str) -> ConversationSession:
        """Async version of restore_expired_session"""
        session = ConversationSession(
            session_id=session_id,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            is_restored=True
        )
        try:
            r = await get_async_redis()
            backup_data = await r.get(f"backup:{session_id}")
            if backup_data:
                preferences = json.loads(backup_data)
                session.user_preferences = {
                    k: set(v) if isinstance(v, list) else v
                    for k, v in preferences.items()
                }
                logger.info(f"Restored preferences (async) for session {session_id}")
            else:
                logger.info(f"No backup preferences found for session {session_id}")
        except Exception as e:
            logger.error(f"Async error restoring preferences for {session_id}: {e}")
        return session

    async def asave_session_with_backup(self, session: ConversationSession):
        """Async version of save_session_with_backup"""
        try:
            session.update_activity()
            r = await get_async_redis()

            await r.setex(
                f"session:{session.session_id}",
                self.session_ttl,
                session.to_json()
            )

            if session.user_preferences:
                preferences_backup = {
                    k: list(v) if isinstance(v, set) else v
                    for k, v in session.user_preferences.items()
                }
                await r.setex(
                    f"backup:{session.session_id}",
                    self.backup_ttl,
                    json.dumps(preferences_backup)
                )

            logger.info(f"Session saved (async): {session.session_id}")
        except Exception as e:
            logger.error(f"Async error saving session {session.session_id}: {e}")
            raise


# Глобальный экземпляр менеджера сессий
_session_manager = None

def get_session_manager() -> ImprovedSessionManager:
    """Получить глобальный экземпляр session manager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = ImprovedSessionManager()
    return _session_manager