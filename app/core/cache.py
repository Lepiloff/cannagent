import os
import json
import hashlib
from typing import Optional, Any, List
try:
    from aiocache import Cache  # type: ignore[import-not-found]
    from aiocache.serializers import JsonSerializer  # type: ignore[import-not-found]
except Exception:  # type: ignore
    Cache = None  # type: ignore
    JsonSerializer = None  # type: ignore
from app.core.logging import get_logger
try:
    import redis  # type: ignore[import-not-found]
except Exception:  # type: ignore
    redis = None  # type: ignore

logger = get_logger(__name__)


class CacheService:
    """Redis-based caching service for embeddings and responses."""
    
    def __init__(self):
        if Cache and JsonSerializer:
            self.cache = Cache(
                Cache.REDIS,
                endpoint=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=int(os.getenv('REDIS_DB', '0')),
                serializer=JsonSerializer(),
            )
        else:
            self.cache = None
    
    def _generate_cache_key(self, prefix: str, data: str) -> str:
        """Generate a cache key from text data."""
        hash_obj = hashlib.md5(data.encode())
        return f"{prefix}:{hash_obj.hexdigest()}"
    
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding for text."""
        cache_key = self._generate_cache_key("embedding", text)
        try:
            if not self.cache:
                return None
            embedding = await self.cache.get(cache_key)
            if embedding:
                logger.debug("Cache hit for embedding", text_length=len(text))
                return embedding
        except Exception as e:
            logger.warning("Cache get failed", error=str(e))
        
        logger.debug("Cache miss for embedding", text_length=len(text))
        return None
    
    async def set_embedding(self, text: str, embedding: List[float]) -> bool:
        """Cache embedding for text."""
        cache_key = self._generate_cache_key("embedding", text)
        try:
            if not self.cache:
                return False
            await self.cache.set(cache_key, embedding, ttl=int(os.getenv('CACHE_TTL', '300')))
            logger.debug("Cached embedding", text_length=len(text))
            return True
        except Exception as e:
            logger.warning("Cache set failed", error=str(e))
            return False

    # ---------- Persistent simple helpers for sync Redis users ----------
    def get_persistent(self, key: str) -> Optional[str]:
        try:
            r = get_redis()
            return r.get(key)
        except Exception:
            return None

    def set_persistent(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        try:
            r = get_redis()
            if ttl is not None:
                r.setex(key, ttl, value)
            else:
                r.set(key, value)
            return True
        except Exception:
            return False
    
    async def get_response(self, query: str, context: str) -> Optional[str]:
        """Get cached response for query and context."""
        cache_key = self._generate_cache_key("response", f"{query}:{context}")
        try:
            response = await self.cache.get(cache_key)
            if response:
                logger.debug("Cache hit for response", query_length=len(query))
                return response
        except Exception as e:
            logger.warning("Cache get failed", error=str(e))
        
        logger.debug("Cache miss for response", query_length=len(query))
        return None
    
    async def set_response(self, query: str, context: str, response: str) -> bool:
        """Cache response for query and context."""
        cache_key = self._generate_cache_key("response", f"{query}:{context}")
        try:
            await self.cache.set(cache_key, response, ttl=int(os.getenv('CACHE_TTL', '300')))
            logger.debug("Cached response", query_length=len(query))
            return True
        except Exception as e:
            logger.warning("Cache set failed", error=str(e))
            return False
    
    async def clear_cache(self) -> bool:
        """Clear all cached data."""
        try:
            await self.cache.clear()
            logger.info("Cache cleared")
            return True
        except Exception as e:
            logger.error("Cache clear failed", error=str(e))
            return False
    
    async def get_stats(self) -> dict:
        """Get cache statistics."""
        try:
            # This would need implementation based on Redis info
            return {
                "status": "connected",
                "host": os.getenv('REDIS_HOST', 'redis'),
                "port": int(os.getenv('REDIS_PORT', '6379')),
                "db": int(os.getenv('REDIS_DB', '0'))
            }
        except Exception as e:
            logger.error("Failed to get cache stats", error=str(e))
            return {"status": "error", "error": str(e)}


# Global cache instance
cache_service = CacheService()


def get_redis() -> redis.Redis:
    """Get synchronous Redis client for session management"""
    if not redis:
        raise RuntimeError("redis client is not available")
    return redis.Redis(
        host=os.getenv('REDIS_HOST', 'redis'),
        port=int(os.getenv('REDIS_PORT', '6379')),
        db=int(os.getenv('REDIS_DB', '0')),
        decode_responses=True  # Автоматически декодировать ответы как строки
    ) 