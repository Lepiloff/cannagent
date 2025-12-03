import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.models.database import Base

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
    """Проверка подключения к базе данных"""
    try:
        with engine.connect() as conn:
            # Проверяем подключение и наличие таблиц
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            
            # Дополнительно проверяем наличие таблицы strains_strain
            result = conn.execute(text("SELECT COUNT(*) FROM strains_strain"))
            count = result.fetchone()[0]
            print(f"Database connection OK. Found {count} strains in database.")
            
            return True
    except Exception as e:
        print(f"Database connection error: {e}")
        return False 