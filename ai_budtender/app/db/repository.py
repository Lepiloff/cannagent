from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.database import Product as ProductModel
from app.models.schemas import ProductCreate
from pgvector.sqlalchemy import Vector
from sqlalchemy import text


class ProductRepository:
    """Репозиторий для работы с товарами"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_product(self, product: ProductCreate, embedding: List[float]) -> ProductModel:
        """Создание нового товара с эмбеддингом"""
        db_product = ProductModel(
            name=product.name,
            description=product.description,
            embedding=embedding
        )
        self.db.add(db_product)
        self.db.commit()
        self.db.refresh(db_product)
        return db_product
    
    def get_product(self, product_id: int) -> Optional[ProductModel]:
        """Получение товара по ID"""
        return self.db.query(ProductModel).filter(ProductModel.id == product_id).first()
    
    def get_products(self, skip: int = 0, limit: int = 100) -> List[ProductModel]:
        """Получение списка товаров"""
        return self.db.query(ProductModel).offset(skip).limit(limit).all()
    
    def search_similar_products(self, query_embedding: List[float], limit: int = 5) -> List[ProductModel]:
        """Поиск товаров по векторному сходству"""
        # Используем cosine distance для поиска похожих товаров
        return (
            self.db.query(ProductModel)
            .filter(ProductModel.embedding.isnot(None))
            .order_by(ProductModel.embedding.cosine_distance(query_embedding))
            .limit(limit)
            .all()
        )
    
    def update_product_embedding(self, product_id: int, embedding: List[float]) -> Optional[ProductModel]:
        """Обновление эмбеддинга товара"""
        product = self.get_product(product_id)
        if product:
            product.embedding = embedding
            self.db.commit()
            self.db.refresh(product)
        return product
    
    def delete_product(self, product_id: int) -> bool:
        """Удаление товара"""
        product = self.get_product(product_id)
        if product:
            self.db.delete(product)
            self.db.commit()
            return True
        return False 