import json
import csv
from typing import List, Dict, Any
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.repository import ProductRepository
from app.core.rag_service import RAGService
from app.models.schemas import ProductCreate


def import_products_from_csv(csv_path: str) -> int:
    """Импорт товаров из CSV файла"""
    count = 0
    db = SessionLocal()
    
    try:
        repository = ProductRepository(db)
        rag_service = RAGService(repository)
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                product = ProductCreate(
                    name=row['name'],
                    description=row['description']
                )
                
                # Создаем товар без эмбеддинга
                created_product = repository.create_product(product, [])
                
                # Генерируем эмбеддинг
                rag_service.add_product_embeddings(created_product.id)
                
                count += 1
                print(f"Импортирован товар: {product.name}")
                
    except Exception as e:
        print(f"Ошибка при импорте: {e}")
    finally:
        db.close()
    
    return count


def import_products_from_json(json_path: str) -> int:
    """Импорт товаров из JSON файла"""
    count = 0
    db = SessionLocal()
    
    try:
        repository = ProductRepository(db)
        rag_service = RAGService(repository)
        
        with open(json_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
            for item in data:
                product = ProductCreate(
                    name=item['name'],
                    description=item['description']
                )
                
                # Создаем товар без эмбеддинга
                created_product = repository.create_product(product, [])
                
                # Генерируем эмбеддинг
                rag_service.add_product_embeddings(created_product.id)
                
                count += 1
                print(f"Импортирован товар: {product.name}")
                
    except Exception as e:
        print(f"Ошибка при импорте: {e}")
    finally:
        db.close()
    
    return count


def create_sample_data() -> List[Dict[str, Any]]:
    """Create sample data for testing"""
    return [
        {
            "name": "Blue Dream",
            "description": "Sativa-Indica hybrid (60/40). Provides relaxing effects with creative uplift. Perfect for daytime use. Sweet berry aroma with pine notes."
        },
        {
            "name": "Northern Lights",
            "description": "Classic indica strain. Strong relaxing effect, helps with insomnia and stress. Best suited for evening use. Earthy aroma with pine notes."
        },
        {
            "name": "Sour Diesel",
            "description": "Energetic sativa. Provides invigorating and creative effects. Great for daytime use. Characteristic diesel aroma with citrus notes."
        },
        {
            "name": "OG Kush",
            "description": "Indica-dominant hybrid. Balanced relaxation and euphoria effects. Suitable for any time of day. Complex aroma with lemon and pine notes."
        },
        {
            "name": "Green Crack",
            "description": "Powerful sativa. Provides energetic and focused effects. Perfect for active daytime activities. Sweet fruity aroma with tropical notes."
        },
        {
            "name": "Wedding Cake",
            "description": "Indica-dominant hybrid. Relaxing effect with mild euphoria. Suitable for evening relaxation. Sweet vanilla aroma with earthy notes."
        },
        {
            "name": "Jack Herer",
            "description": "Balanced hybrid. Provides mental clarity and creative uplift. Suitable for daytime use. Spicy aroma with pine and citrus notes."
        },
        {
            "name": "Granddaddy Purple",
            "description": "Powerful indica. Strong relaxing effect, helps with pain and insomnia. Perfect for evening use. Sweet berry aroma with grape notes."
        }
    ]


def initialize_sample_data():
    """Инициализация базы данных примерными данными"""
    db = SessionLocal()
    
    try:
        repository = ProductRepository(db)
        rag_service = RAGService(repository)
        
        # Проверяем, есть ли уже данные
        existing_products = repository.get_products(limit=1)
        if existing_products:
            print("Данные уже существуют в базе данных")
            return
        
        sample_data = create_sample_data()
        
        for item in sample_data:
            product = ProductCreate(
                name=item['name'],
                description=item['description']
            )
            
            # Создаем товар без эмбеддинга
            created_product = repository.create_product(product, [])
            
            # Генерируем эмбеддинг
            rag_service.add_product_embeddings(created_product.id)
            
            print(f"Создан товар: {product.name}")
            
    except Exception as e:
        print(f"Ошибка при инициализации данных: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # Инициализация базы данных примерными данными
    initialize_sample_data() 