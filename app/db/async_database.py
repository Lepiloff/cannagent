from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os
from app.core.logging import get_logger

logger = get_logger(__name__)

# Create async engine
async_engine = create_async_engine(
    os.getenv('DATABASE_URL', 'postgresql://user:password@db:5432/ai_budtender').replace("postgresql://", "postgresql+asyncpg://"),
    echo=os.getenv('DEBUG', 'false').lower() == 'true',
    max_overflow=int(os.getenv('MAX_CONNECTIONS', '100')),
    pool_size=int(os.getenv('MAX_CONNECTIONS', '100')) // 2,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Dependency for async database sessions
async def get_async_db():
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error("Database session error", error=str(e))
            await session.rollback()
            raise
        finally:
            await session.close()

# Check async database connection
async def check_async_db_connection():
    """Check async database connection."""
    try:
        async with async_engine.begin() as conn:
            await conn.execute("SELECT 1")
        logger.info("Async database connection successful")
        return True
    except Exception as e:
        logger.error("Async database connection failed", error=str(e))
        return False

# Create tables async
async def create_async_tables():
    """Create database tables asynchronously."""
    from app.models.database import Base
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error("Failed to create database tables", error=str(e))
        raise 