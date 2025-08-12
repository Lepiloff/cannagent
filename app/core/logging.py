import structlog
import logging
import sys
from typing import Any, Dict
import os


def setup_logging() -> None:
    """Configure structured logging for the application."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if os.getenv('LOG_FORMAT', 'json') == "json" else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper()),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LoggingMiddleware:
    """Middleware for logging HTTP requests and responses."""
    
    def __init__(self, app):
        self.app = app
        self.logger = get_logger("http")
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request_id = scope.get("headers", {}).get("x-request-id", "unknown")
            
            # Log request
            self.logger.info(
                "HTTP request started",
                method=scope["method"],
                path=scope["path"],
                query_string=scope.get("query_string", b"").decode(),
                request_id=request_id,
            )
            
            # Process request
            await self.app(scope, receive, send)
            
            # Log response (simplified, would need more work for full response logging)
            self.logger.info(
                "HTTP request completed",
                method=scope["method"],
                path=scope["path"],
                request_id=request_id,
            )
        else:
            await self.app(scope, receive, send) 