"""
Enhanced data import utilities for strain management.
Legacy product import functions have been replaced by sync_strain_relations.py
"""

from typing import List, Dict, Any
from app.db.database import SessionLocal
from app.db.repository import StrainRepository
from app.core.rag_service import RAGService


def create_sample_strains() -> List[Dict[str, Any]]:
    """Create sample strain data for testing"""
    return [
        {
            "name": "Blue Dream",
            "title": "Blue Dream - Balanced Hybrid",
            "description": "Sativa-Indica hybrid (60/40). Provides relaxing effects with creative uplift. Perfect for daytime use.",
            "text_content": "Blue Dream is one of the most popular strains. Sweet berry aroma with pine notes. Great for creativity and relaxation.",
            "thc": 17.0,
            "cbd": 0.2,
            "category": "Hybrid",
            "active": True,
            "slug": "blue-dream"
        },
        {
            "name": "Northern Lights",
            "title": "Northern Lights - Classic Indica",
            "description": "Classic indica strain. Strong relaxing effect, helps with insomnia and stress. Best suited for evening use.",
            "text_content": "Northern Lights is perfect for evening relaxation and sleep. Earthy aroma with pine notes.",
            "thc": 18.5,
            "cbd": 0.1,
            "category": "Indica",
            "active": True,
            "slug": "northern-lights"
        },
        {
            "name": "Sour Diesel",
            "title": "Sour Diesel - Energizing Sativa",
            "description": "Energetic sativa. Provides invigorating and creative effects. Great for daytime use.",
            "text_content": "Sour Diesel is ideal for daytime energy and focus. Characteristic diesel aroma with citrus notes.",
            "thc": 20.0,
            "cbd": 0.1,
            "category": "Sativa",
            "active": True,
            "slug": "sour-diesel"
        },
        {
            "name": "OG Kush",
            "title": "OG Kush - Premium Hybrid",
            "description": "Indica-dominant hybrid. Balanced relaxation and euphoria effects. Suitable for any time of day.",
            "text_content": "OG Kush offers complex effects and aroma with lemon and pine notes.",
            "thc": 19.0,
            "cbd": 0.3,
            "category": "Hybrid",
            "active": True,
            "slug": "og-kush"
        },
        {
            "name": "Green Crack",
            "title": "Green Crack - Energetic Sativa",
            "description": "Powerful sativa. Provides energetic and focused effects. Perfect for active daytime activities.",
            "text_content": "Green Crack delivers energy and focus. Sweet fruity aroma with tropical notes.",
            "thc": 21.0,
            "cbd": 0.1,
            "category": "Sativa",
            "active": True,
            "slug": "green-crack"
        }
    ]


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
        repository = StrainRepository(db)
        rag_service = RAGService(repository)
        
        # Проверяем, есть ли уже штаммы
        existing_strains = repository.get_strains(limit=1)
        if existing_strains:
            print("Данные о штаммах уже существуют в базе данных")
            return
        
        # Создаем штаммы
        sample_strains = create_sample_strains()
        
        for strain_data in sample_strains:
            # Создаем штамм без эмбеддинга (мок-режим не генерирует эмбеддинги)
            created_strain = repository.create_strain(strain_data, None)
            
            # В мок-режиме не генерируем эмбеддинги, чтобы избежать ошибок
            try:
                rag_service.add_strain_embeddings(created_strain.id)
                print(f"Создан штамм с эмбеддингом: {strain_data['name']}")
            except Exception as e:
                # В мок-режиме просто пропускаем генерацию эмбеддинга
                print(f"Создан штамм без эмбеддинга (мок-режим): {strain_data['name']}")
            
    except Exception as e:
        print(f"Ошибка при инициализации данных: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # Инициализация базы данных примерными данными
    initialize_sample_data() 
