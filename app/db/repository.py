from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.database import Strain as StrainModel
from app.models.schemas import StrainCreate
from pgvector.sqlalchemy import Vector
from sqlalchemy import text


class StrainRepository:
    """Репозиторий для работы со штаммами"""
    
    def __init__(self, db: Session):
        self.db = db
    def get_strain(self, strain_id: int) -> Optional[StrainModel]:
        """Получение штамма по ID"""
        return self.db.query(StrainModel).filter(StrainModel.id == strain_id).first()
    
    def get_strains(self, skip: int = 0, limit: int = 100) -> List[StrainModel]:
        """Получение списка штаммов"""
        return self.db.query(StrainModel).filter(StrainModel.active == True).offset(skip).limit(limit).all()
    
    def search_similar_strains(self, query_embedding: List[float], limit: int = 5) -> List[StrainModel]:
        """Поиск штаммов по векторному сходству"""
        return (
            self.db.query(StrainModel)
            .filter(StrainModel.embedding.isnot(None))
            .filter(StrainModel.active == True)
            .order_by(StrainModel.embedding.cosine_distance(query_embedding))
            .limit(limit)
            .all()
        )
    
    def update_strain_embedding(self, strain_id: int, embedding: List[float]) -> Optional[StrainModel]:
        """Обновление эмбеддинга штамма"""
        strain = self.get_strain(strain_id)
        if strain:
            strain.embedding = embedding
            self.db.commit()
            self.db.refresh(strain)
        return strain
    
    def create_strain(self, strain_data: dict, embedding: Optional[List[float]] = None) -> StrainModel:
        """Создание нового штамма с эмбеддингом"""
        db_strain = StrainModel(
            name=strain_data["name"],
            title=strain_data.get("title"),
            description=strain_data.get("description"),
            text_content=strain_data.get("text_content"),
            keywords=strain_data.get("keywords"),
            cbd=strain_data.get("cbd"),
            thc=strain_data.get("thc"),
            cbg=strain_data.get("cbg"),
            rating=strain_data.get("rating"),
            category=strain_data.get("category"),
            img=strain_data.get("img"),
            img_alt_text=strain_data.get("img_alt_text"),
            active=strain_data.get("active", True),
            top=strain_data.get("top", False),
            main=strain_data.get("main", False),
            is_review=strain_data.get("is_review", False),
            slug=strain_data.get("slug"),
            embedding=embedding
        )
        self.db.add(db_strain)
        self.db.commit()
        self.db.refresh(db_strain)
        return db_strain 