from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from typing import Callable
import time
import os
from app.core.logging import get_logger

logger = get_logger(__name__)

# Metrics definitions
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

CHAT_REQUESTS = Counter(
    'chat_requests_total',
    'Total chat requests',
    ['status']
)

EMBEDDING_REQUESTS = Counter(
    'embedding_requests_total',
    'Total embedding requests',
    ['cache_hit']
)

VECTOR_SEARCH_DURATION = Histogram(
    'vector_search_duration_seconds',
    'Vector search duration in seconds'
)

DATABASE_CONNECTIONS = Gauge(
    'database_connections_active',
    'Number of active database connections'
)


class MetricsMiddleware:
    """Middleware for collecting HTTP metrics."""
    
    def __init__(self, app: Callable):
        self.app = app
    
    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        if scope["type"] == "http":
            start_time = time.time()
            ACTIVE_REQUESTS.inc()
            
            # Create a custom send function to capture response
            status_code = 200
            
            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)
            
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                # Record metrics
                duration = time.time() - start_time
                method = scope["method"]
                path = scope["path"]
                
                REQUEST_COUNT.labels(
                    method=method,
                    endpoint=path,
                    status_code=status_code
                ).inc()
                
                REQUEST_DURATION.labels(
                    method=method,
                    endpoint=path
                ).observe(duration)
                
                ACTIVE_REQUESTS.dec()
                
                logger.debug(
                    "HTTP request metrics recorded",
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration=duration
                )
        else:
            await self.app(scope, receive, send)


def record_chat_request(status: str):
    """Record a chat request metric."""
    CHAT_REQUESTS.labels(status=status).inc()


def record_embedding_request(cache_hit: bool):
    """Record an embedding request metric."""
    EMBEDDING_REQUESTS.labels(cache_hit=str(cache_hit).lower()).inc()


def record_vector_search_duration(duration: float):
    """Record vector search duration."""
    VECTOR_SEARCH_DURATION.observe(duration)


def record_database_connections(count: int):
    """Record current database connections."""
    DATABASE_CONNECTIONS.set(count)


async def get_metrics() -> Response:
    """Get Prometheus metrics."""
    if not os.getenv('ENABLE_METRICS', 'true').lower() == 'true':
        return Response(content="Metrics disabled", status_code=404)
    
    try:
        metrics_data = generate_latest()
        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST
        )
    except Exception as e:
        logger.error("Failed to generate metrics", error=str(e))
        return Response(content="Error generating metrics", status_code=500) 