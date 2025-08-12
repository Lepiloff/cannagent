from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException
import os
from app.core.logging import get_logger

logger = get_logger(__name__)

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{os.getenv('RATE_LIMIT_REQUESTS', '100')}/{os.getenv('RATE_LIMIT_PERIOD', '60')}minute"]
)

# Rate limit decorator for endpoints
def rate_limit(rate: str):
    """Decorator to apply rate limiting to endpoints."""
    return limiter.limit(rate)

# Common rate limits
rate_limit_requests = int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
rate_limit_period = int(os.getenv('RATE_LIMIT_PERIOD', '60'))

CHAT_RATE_LIMIT = f"{rate_limit_requests // 4}/{rate_limit_period}minute"
PRODUCTS_RATE_LIMIT = f"{rate_limit_requests // 2}/{rate_limit_period}minute"
HEALTH_RATE_LIMIT = f"{rate_limit_requests * 2}/{rate_limit_period}minute"

async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Custom rate limit exceeded handler."""
    logger.warning(
        "Rate limit exceeded",
        client_ip=get_remote_address(request),
        path=request.url.path,
        method=request.method,
        rate_limit=str(exc.detail)
    )
    
    response = {
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later.",
        "retry_after": exc.retry_after
    }
    
    raise HTTPException(
        status_code=429,
        detail=response,
        headers={"Retry-After": str(exc.retry_after)}
    ) 