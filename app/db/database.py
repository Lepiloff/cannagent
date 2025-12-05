import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.models.database import Base

logger = logging.getLogger(__name__)

# Динамическая сборка DATABASE_URL из переменных окружения
def get_database_url():
    user = os.getenv('POSTGRES_USER', 'postgres')
    password = os.getenv('POSTGRES_PASSWORD', 'password')
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    db_name = os.getenv('POSTGRES_DB', 'postgres')

    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

# Создаем движок для синхронной работы с БД (cannamente database)
database_url = os.getenv('DATABASE_URL') or get_database_url()
engine = create_engine(database_url)

# Создаем сессию
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создаем таблицы
def create_tables():
    """Создание всех таблиц в БД"""
    Base.metadata.create_all(bind=engine)

# Dependency для получения сессии БД
def get_db():
    """Генератор сессий БД для использования в FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Проверка подключения к БД
def check_db_connection():
    """Проверка подключения к базе данных (logs only errors)"""
    try:
        with engine.connect() as conn:
            # Быстрая проверка подключения
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            return True
    except Exception as e:
        # Логируем ТОЛЬКО ошибки подключения
        logger.error(f"❌ Database connection failed: {e}")
        return False 