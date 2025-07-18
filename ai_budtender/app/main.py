from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.db.database import create_tables
from app.api import chat, health, products
from app.utils.data_import import initialize_sample_data
from app.core.logging import setup_logging
from app.core.metrics import MetricsMiddleware, get_metrics
from app.core.rate_limiter import rate_limit_handler

# Setup logging
setup_logging()

# Create FastAPI application
app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    description="AI Budtender - Smart assistant for cannabis product selection",
    openapi_url=f"{settings.api_v1_str}/openapi.json",
    docs_url=f"{settings.api_v1_str}/docs",
    redoc_url=f"{settings.api_v1_str}/redoc"
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
if settings.enable_metrics:
    app.add_middleware(MetricsMiddleware)

# Add rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_requests}/{settings.rate_limit_period}minute"]
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Include routers
app.include_router(
    chat.router,
    prefix=f"{settings.api_v1_str}/chat",
    tags=["chat"]
)

app.include_router(
    health.router,
    prefix=f"{settings.api_v1_str}",
    tags=["health"]
)

app.include_router(
    products.router,
    prefix=f"{settings.api_v1_str}/products",
    tags=["products"]
)

# Add metrics endpoint
if settings.enable_metrics:
    app.add_api_route("/metrics", get_metrics, methods=["GET"], tags=["monitoring"])


@app.on_event("startup")
async def startup_event():
    """Application startup initialization"""
    # Create database tables
    create_tables()
    
    # Initialize sample data
    initialize_sample_data()
    
    print(f"🚀 {settings.project_name} started!")
    print(f"📚 Documentation available at: {settings.api_v1_str}/docs")
    if settings.enable_metrics:
        print(f"📊 Metrics available at: /metrics")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Budtender API", 
        "version": "1.0.0",
        "docs": f"{settings.api_v1_str}/docs",
        "metrics": "/metrics" if settings.enable_metrics else None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, debug=settings.debug) 