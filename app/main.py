import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.db.database import create_tables, SessionLocal
from app.api import chat, health, strains
from app.utils.data_import import initialize_sample_data
from app.core.logging import setup_logging
from app.core.metrics import MetricsMiddleware, get_metrics
from app.core.rate_limiter import rate_limit_handler
from app.core.cache import get_redis
from app.core.taxonomy_init import initialize_taxonomy_system

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan event handler"""
    # Startup
    logger.info("🚀 Starting AI Budtender application...")

    create_tables()
    # initialize_sample_data()  # Disabled - using real data from cannamente

    # Initialize DB-Aware Taxonomy System
    try:
        db_session = SessionLocal()
        redis_client = get_redis()

        taxonomy_system = initialize_taxonomy_system(
            db_session=db_session,
            redis_client=redis_client,
            warm_cache=True
        )

        if taxonomy_system:
            logger.info("✅ Taxonomy system initialized successfully")
        else:
            logger.warning("⚠️ Taxonomy system not initialized (disabled)")

    except Exception as e:
        logger.error(f"❌ Failed to initialize taxonomy system: {e}")
        logger.warning("Application will continue without taxonomy cache")

    logger.info("✅ Application startup complete")

    yield

    # Shutdown (if needed)
    logger.info("👋 Shutting down application...")

# Create FastAPI application
app = FastAPI(
    lifespan=lifespan,
    title=os.getenv('PROJECT_NAME', 'AI Budtender'),
    version="1.0.0",
    description="AI Budtender - Smart assistant for cannabis product selection",
    openapi_url=f"{os.getenv('API_V1_STR', '/api/v1')}/openapi.json",
    docs_url=f"{os.getenv('API_V1_STR', '/api/v1')}/docs",
    redoc_url=f"{os.getenv('API_V1_STR', '/api/v1')}/redoc"
)

# Add middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics middleware
enable_metrics = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
if enable_metrics:
    app.add_middleware(MetricsMiddleware)

# Add rate limiting
rate_limit_requests = int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
rate_limit_period = int(os.getenv('RATE_LIMIT_PERIOD', '60'))
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{rate_limit_requests}/{rate_limit_period}minute"]
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Include routers
api_v1_str = os.getenv('API_V1_STR', '/api/v1')
app.include_router(
    chat.router,
    prefix=f"{api_v1_str}/chat",
    tags=["chat"]
)

app.include_router(
    health.router,
    prefix=f"{api_v1_str}",
    tags=["health"]
)

app.include_router(
    strains.router,
    prefix=f"{api_v1_str}/strains", 
    tags=["strains"]
)

# Add metrics endpoint
if enable_metrics:
    app.add_api_route("/metrics", get_metrics, methods=["GET"], tags=["monitoring"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Budtender API", 
        "version": "1.0.0",
        "docs": f"{api_v1_str}/docs",
        "metrics": "/metrics" if enable_metrics else None
    }


if __name__ == "__main__":
    import uvicorn
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    uvicorn.run(app, host="0.0.0.0", port=8000, debug=debug) 