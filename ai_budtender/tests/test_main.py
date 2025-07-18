import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import get_db
from app.models.database import Base

# Создаем тестовую БД в памяти
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_root():
    """Тест корневого эндпоинта"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "AI Budtender API"


def test_health_check():
    """Тест health check"""
    response = client.get("/api/v1/ping/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_get_products():
    """Тест получения списка товаров"""
    response = client.get("/api/v1/products/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_create_product():
    """Тест создания товара"""
    product_data = {
        "name": "Test Product",
        "description": "Test Description"
    }
    response = client.post("/api/v1/products/", json=product_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == product_data["name"]
    assert data["description"] == product_data["description"]
    assert "id" in data


def test_chat_ask():
    """Тест запроса к чату"""
    chat_data = {
        "message": "Посоветуй что-нибудь для расслабления",
        "history": []
    }
    response = client.post("/api/v1/chat/ask/", json=chat_data)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "recommended_products" in data
    assert isinstance(data["recommended_products"], list)


def test_get_product_not_found():
    """Тест получения несуществующего товара"""
    response = client.get("/api/v1/products/999999")
    assert response.status_code == 404 