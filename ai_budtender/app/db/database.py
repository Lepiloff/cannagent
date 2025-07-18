from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.config import settings
from app.models.database import Base

# Создаем движок для синхронной работы с БД
engine = create_engine(settings.database_url)

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
    """Проверка подключения к базе данных"""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False 