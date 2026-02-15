from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from app.models.database import (
    Strain as StrainModel, 
    Feeling, 
    HelpsWith, 
    Negative, 
    Flavor, 
    Terpene
)
from pgvector.sqlalchemy import Vector


class StrainRepository:
    """Enhanced repository for strain operations with structured filtering"""
    
    def __init__(self, db: Session):
        self.db = db
    def get_strain(self, strain_id: int) -> Optional[StrainModel]:
        """Получение штамма по ID"""
        return self.db.query(StrainModel).filter(StrainModel.id == strain_id).first()

    def get_strain_by_id(self, strain_id: int) -> Optional[StrainModel]:
        """Alias for get_strain() for compatibility with RAGService"""
        return self.get_strain(strain_id)

    def get_strains(self, skip: int = 0, limit: int = 100) -> List[StrainModel]:
        """Получение списка штаммов"""
        return self.db.query(StrainModel).filter(StrainModel.active == True).offset(skip).limit(limit).all()
    
    def update_strain_embedding(self, strain_id: int, embedding: List[float], language: str = 'en') -> Optional[StrainModel]:
        """Обновление эмбеддинга штамма для указанного языка"""
        strain = self.get_strain(strain_id)
        if strain:
            if language == 'en':
                strain.embedding_en = embedding
            else:
                strain.embedding_es = embedding
            self.db.commit()
            self.db.refresh(strain)
        return strain
    
    def get_strain_with_relations(self, strain_id: int) -> Optional[StrainModel]:
        """Get strain with all related data loaded"""
        return (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .options(joinedload(StrainModel.terpenes))
            .filter(StrainModel.id == strain_id)
            .first()
        )
    
    def get_strains_with_relations(self, skip: int = 0, limit: int = 100) -> List[StrainModel]:
        """Get strains list with all relations loaded"""
        return (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .options(joinedload(StrainModel.terpenes))  # STAGE 2: Include terpenes
            .filter(StrainModel.active == True)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    # Helper methods for managing reference data
    def get_all_feelings(self) -> List[Feeling]:
        """Get all available feelings"""
        return self.db.query(Feeling).order_by(Feeling.name).all()
    
    def get_all_helps_with(self) -> List[HelpsWith]:
        """Get all available medical conditions"""
        return self.db.query(HelpsWith).order_by(HelpsWith.name).all()
    
    def get_all_negatives(self) -> List[Negative]:
        """Get all negative effects"""
        return self.db.query(Negative).order_by(Negative.name).all()
    
    def get_all_flavors(self) -> List[Flavor]:
        """Get all flavors"""
        return self.db.query(Flavor).order_by(Flavor.name).all()
    
    def create_or_get_feeling(self, name: str, energy_type: str) -> Feeling:
        """Create or get existing feeling"""
        feeling = self.db.query(Feeling).filter(Feeling.name == name).first()
        if not feeling:
            feeling = Feeling(name=name, energy_type=energy_type)
            self.db.add(feeling)
            self.db.commit()
            self.db.refresh(feeling)
        return feeling
    
    def create_or_get_helps_with(self, name: str) -> HelpsWith:
        """Create or get existing helps_with condition"""
        condition = self.db.query(HelpsWith).filter(HelpsWith.name == name).first()
        if not condition:
            condition = HelpsWith(name=name)
            self.db.add(condition)
            self.db.commit()
            self.db.refresh(condition)
        return condition
    
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
            embedding_en=embedding,
            embedding_es=embedding
        )
        self.db.add(db_strain)
        self.db.commit()
        self.db.refresh(db_strain)
        return db_strain
    
    def update_strain_relations(self, strain: StrainModel,
                              feelings: List[str] = None,
                              helps_with: List[str] = None,
                              negatives: List[str] = None,
                              flavors: List[str] = None,
                              terpenes: List[str] = None) -> StrainModel:
        """Update strain relations from cannamente data"""
        
        # Update feelings
        if feelings:
            strain.feelings.clear()
            for feeling_name in feelings:
                # Try to get existing feeling (seeded from migration), or create with default energy_type
                feeling = self.db.query(Feeling).filter(Feeling.name == feeling_name).first()
                if not feeling:
                    # Default to 'neutral' for new feelings (most should exist from migration seed data)
                    feeling = self.create_or_get_feeling(feeling_name, 'neutral')
                strain.feelings.append(feeling)
        
        # Update helps_with
        if helps_with:
            strain.helps_with.clear()
            for condition_name in helps_with:
                condition = self.create_or_get_helps_with(condition_name)
                strain.helps_with.append(condition)
        
        # Update negatives
        if negatives:
            strain.negatives.clear()
            for negative_name in negatives:
                negative = self.db.query(Negative).filter(Negative.name == negative_name).first()
                if not negative:
                    negative = Negative(name=negative_name)
                    self.db.add(negative)
                    self.db.commit()
                    self.db.refresh(negative)
                strain.negatives.append(negative)
        
        # Update flavors
        if flavors:
            strain.flavors.clear()
            for flavor_name in flavors:
                flavor = self.db.query(Flavor).filter(Flavor.name == flavor_name).first()
                if not flavor:
                    flavor = Flavor(name=flavor_name)
                    self.db.add(flavor)
                    self.db.commit()
                    self.db.refresh(flavor)
                strain.flavors.append(flavor)

        # Update terpenes
        if terpenes:
            strain.terpenes.clear()
            for terpene_name in terpenes:
                terpene = self.db.query(Terpene).filter(Terpene.name == terpene_name).first()
                if not terpene:
                    terpene = Terpene(name=terpene_name)
                    self.db.add(terpene)
                    self.db.commit()
                    self.db.refresh(terpene)
                strain.terpenes.append(terpene)

        self.db.commit()
        self.db.refresh(strain)
        return strain
