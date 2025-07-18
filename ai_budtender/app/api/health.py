from fastapi import APIRouter, Request
from datetime import datetime
from app.db.database import check_db_connection
from app.models.schemas import HealthResponse, CacheStatsResponse
from app.core.cache import cache_service
from app.core.rate_limiter import HEALTH_RATE_LIMIT, limiter

router = APIRouter()


@router.get("/ping/", response_model=HealthResponse)
@limiter.limit(HEALTH_RATE_LIMIT)
async def health_check(request: Request):
    """
    Health check endpoint
    """
    db_status = "ok" if check_db_connection() else "error"
    
    # Check Redis cache status
    cache_stats = await cache_service.get_stats()
    redis_status = cache_stats.get("status", "unknown")
    
    return HealthResponse(
        status="ok",
        database=db_status,
        redis=redis_status,
        timestamp=datetime.now()
    )


@router.get("/cache/stats/", response_model=CacheStatsResponse)
@limiter.limit(HEALTH_RATE_LIMIT)
async def cache_stats(request: Request):
    """
    Get cache statistics
    """
    stats = await cache_service.get_stats()
    return CacheStatsResponse(**stats)


@router.post("/cache/clear/")
@limiter.limit("5/minute")
async def clear_cache(request: Request):
    """
    Clear all cached data
    """
    success = await cache_service.clear_cache()
    return {"success": success, "message": "Cache cleared" if success else "Failed to clear cache"} 