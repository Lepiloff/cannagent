from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import List, Optional, Dict, Any
from app.models.database import (
    Strain as StrainModel, 
    Feeling, 
    HelpsWith, 
    Negative, 
    Flavor, 
    Terpene
)
from app.core.taxonomy_aliases import canonical_taxonomy_name
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
            .options(joinedload(StrainModel.dominant_terpene))
            .options(joinedload(StrainModel.other_terpenes))
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
            .options(joinedload(StrainModel.dominant_terpene))
            .options(joinedload(StrainModel.other_terpenes))  # STAGE 2: Include terpenes
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
        canonical_name = canonical_taxonomy_name("Feeling", name)
        feeling = self._get_taxonomy_by_name(Feeling, canonical_name)
        if not feeling:
            feeling = Feeling(name=canonical_name, energy_type=energy_type)
            self.db.add(feeling)
            self.db.commit()
            self.db.refresh(feeling)
        return feeling
    
    def create_or_get_helps_with(self, name: str) -> HelpsWith:
        """Create or get existing helps_with condition"""
        canonical_name = canonical_taxonomy_name("HelpsWith", name)
        condition = self._get_taxonomy_by_name(HelpsWith, canonical_name)
        if not condition:
            condition = HelpsWith(name=canonical_name)
            self.db.add(condition)
            self.db.commit()
            self.db.refresh(condition)
        return condition

    def _get_taxonomy_by_name(self, model, name: str):
        """Find taxonomy row by canonical, English, or Spanish name case-insensitively."""
        canonical_name = canonical_taxonomy_name(model.__name__, name)
        normalized = canonical_name.lower()
        conditions = [func.lower(model.name) == normalized]
        if hasattr(model, "name_en"):
            conditions.append(func.lower(model.name_en) == normalized)
        if hasattr(model, "name_es"):
            conditions.append(func.lower(model.name_es) == normalized)
        return self.db.query(model).filter(or_(*conditions)).first()
    
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
                feeling = self._get_taxonomy_by_name(Feeling, feeling_name)
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
                canonical_name = canonical_taxonomy_name("Negative", negative_name)
                negative = self._get_taxonomy_by_name(Negative, canonical_name)
                if not negative:
                    negative = Negative(name=canonical_name)
                    self.db.add(negative)
                    self.db.commit()
                    self.db.refresh(negative)
                strain.negatives.append(negative)
        
        # Update flavors
        if flavors:
            strain.flavors.clear()
            for flavor_name in flavors:
                canonical_name = canonical_taxonomy_name("Flavor", flavor_name)
                flavor = self._get_taxonomy_by_name(Flavor, canonical_name)
                if not flavor:
                    flavor = Flavor(name=canonical_name)
                    self.db.add(flavor)
                    self.db.commit()
                    self.db.refresh(flavor)
                strain.flavors.append(flavor)

        # Update terpenes
        if terpenes:
            strain.dominant_terpene = None
            strain.other_terpenes.clear()
            resolved_terpenes = []
            for terpene_name in terpenes:
                canonical_name = canonical_taxonomy_name("Terpene", terpene_name)
                terpene = self._get_taxonomy_by_name(Terpene, canonical_name)
                if not terpene:
                    # Terpenes are a fixed canna taxonomy with required metadata.
                    # Do not create partial rows from imported/free-form values.
                    continue
                if terpene not in resolved_terpenes:
                    resolved_terpenes.append(terpene)
            if resolved_terpenes:
                strain.dominant_terpene = resolved_terpenes[0]
                strain.other_terpenes.extend(resolved_terpenes[1:])

        self.db.commit()
        self.db.refresh(strain)
        return strain
