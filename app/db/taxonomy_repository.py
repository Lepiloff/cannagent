"""
Taxonomy Repository - Centralized access to taxonomy data

Purpose:
- Query all flavors, feelings, helps_with, negatives, terpenes from database
- Calculate THC/CBD ranges from actual strain data
- Provide bilingual support (EN/ES)
- NO caching logic (separation of concerns)

Design Principles:
- Single Responsibility: ONLY reads taxonomy data
- Dependency Inversion: Interface-based design
- Returns plain dicts (not ORM objects) for easy serialization
"""

from typing import List, Dict, Tuple
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from app.models.database import (
    Flavor,
    Feeling,
    HelpsWith,
    Negative,
    Terpene,
    Strain as StrainModel
)

logger = logging.getLogger(__name__)


class ITaxonomyRepository(ABC):
    """Interface for taxonomy data access (Dependency Inversion Principle)"""

    @abstractmethod
    def get_all_flavors(self) -> List[Dict[str, str]]:
        """
        Get all flavors with bilingual names

        Returns:
            [{"name_en": "tropical", "name_es": "tropical"}, ...]
        """
        pass

    @abstractmethod
    def get_all_feelings(self) -> List[Dict[str, str]]:
        """
        Get all feelings with bilingual names and energy type

        Returns:
            [{"name_en": "relaxed", "name_es": "relajado", "energy_type": "relaxing"}, ...]
        """
        pass

    @abstractmethod
    def get_all_helps_with(self) -> List[Dict[str, str]]:
        """
        Get all medical conditions with bilingual names

        Returns:
            [{"name_en": "pain", "name_es": "dolor"}, ...]
        """
        pass

    @abstractmethod
    def get_all_negatives(self) -> List[Dict[str, str]]:
        """
        Get all negative effects with bilingual names

        Returns:
            [{"name_en": "dry mouth", "name_es": "boca seca"}, ...]
        """
        pass

    @abstractmethod
    def get_all_terpenes(self) -> List[str]:
        """
        Get all terpene names (scientific names, no translation)

        Returns:
            ["Myrcene", "Limonene", "Pinene", ...]
        """
        pass

    @abstractmethod
    def get_thc_range(self) -> Tuple[float, float]:
        """
        Calculate actual THC range from active strains

        Returns:
            (min_thc, max_thc) tuple, e.g., (0.5, 28.3)
        """
        pass

    @abstractmethod
    def get_cbd_range(self) -> Tuple[float, float]:
        """
        Calculate actual CBD range from active strains

        Returns:
            (min_cbd, max_cbd) tuple, e.g., (0.1, 15.2)
        """
        pass

    @abstractmethod
    def get_categories(self) -> List[str]:
        """
        Get available strain categories

        Returns:
            ["Indica", "Sativa", "Hybrid"]
        """
        pass


class TaxonomyRepository(ITaxonomyRepository):
    """
    Concrete implementation of taxonomy repository

    Design Decisions:
    - Returns plain dicts (not ORM objects) for easy serialization
    - Bilingual support with fallback to legacy 'name' field
    - Calculates ranges from actual data (no hardcoded values)
    - Handles NULL values gracefully
    - Ordered results for consistent caching
    - No business logic (pure data access)
    """

    def __init__(self, db_session: Session):
        """
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        logger.debug("TaxonomyRepository initialized")

    def get_all_flavors(self) -> List[Dict[str, str]]:
        """Get all flavors with bilingual names"""
        try:
            flavors = self.db.query(Flavor).order_by(Flavor.name_en).all()

            result = [
                {
                    "name_en": f.name_en or f.name,  # Fallback to legacy name
                    "name_es": f.name_es or f.name
                }
                for f in flavors
            ]

            logger.debug(f"Loaded {len(result)} flavors from database")
            return result

        except Exception as e:
            logger.error(f"Failed to load flavors: {e}")
            return []

    def get_all_feelings(self) -> List[Dict[str, str]]:
        """Get all feelings with bilingual names and energy type"""
        try:
            feelings = self.db.query(Feeling).order_by(Feeling.name_en).all()

            result = [
                {
                    "name_en": f.name_en or f.name,
                    "name_es": f.name_es or f.name,
                    "energy_type": f.energy_type or "neutral"
                }
                for f in feelings
            ]

            logger.debug(f"Loaded {len(result)} feelings from database")
            return result

        except Exception as e:
            logger.error(f"Failed to load feelings: {e}")
            return []

    def get_all_helps_with(self) -> List[Dict[str, str]]:
        """Get all medical conditions with bilingual names"""
        try:
            conditions = self.db.query(HelpsWith).order_by(HelpsWith.name_en).all()

            result = [
                {
                    "name_en": h.name_en or h.name,
                    "name_es": h.name_es or h.name
                }
                for h in conditions
            ]

            logger.debug(f"Loaded {len(result)} medical conditions from database")
            return result

        except Exception as e:
            logger.error(f"Failed to load medical conditions: {e}")
            return []

    def get_all_negatives(self) -> List[Dict[str, str]]:
        """Get all negative effects with bilingual names"""
        try:
            negatives = self.db.query(Negative).order_by(Negative.name_en).all()

            result = [
                {
                    "name_en": n.name_en or n.name,
                    "name_es": n.name_es or n.name
                }
                for n in negatives
            ]

            logger.debug(f"Loaded {len(result)} negative effects from database")
            return result

        except Exception as e:
            logger.error(f"Failed to load negative effects: {e}")
            return []

    def get_all_terpenes(self) -> List[str]:
        """Get all terpene names (scientific names, no translation)"""
        try:
            terpenes = self.db.query(Terpene.name).order_by(Terpene.name).all()

            result = [t.name for t in terpenes if t.name]

            logger.debug(f"Loaded {len(result)} terpenes from database")
            return result

        except Exception as e:
            logger.error(f"Failed to load terpenes: {e}")
            return []

    def get_thc_range(self) -> Tuple[float, float]:
        """
        Calculate actual THC range from active strains

        Returns:
            (min_thc, max_thc) tuple from actual strain data
        """
        try:
            result = self.db.query(
                func.min(StrainModel.thc),
                func.max(StrainModel.thc)
            ).filter(
                StrainModel.active == True,
                StrainModel.thc.isnot(None)
            ).first()

            min_thc = float(result[0]) if result[0] is not None else 0.0
            max_thc = float(result[1]) if result[1] is not None else 30.0

            logger.debug(f"THC range calculated: {min_thc}-{max_thc}%")
            return (min_thc, max_thc)

        except Exception as e:
            logger.error(f"Failed to calculate THC range: {e}")
            return (0.0, 30.0)  # Default fallback

    def get_cbd_range(self) -> Tuple[float, float]:
        """
        Calculate actual CBD range from active strains

        Returns:
            (min_cbd, max_cbd) tuple from actual strain data
        """
        try:
            result = self.db.query(
                func.min(StrainModel.cbd),
                func.max(StrainModel.cbd)
            ).filter(
                StrainModel.active == True,
                StrainModel.cbd.isnot(None)
            ).first()

            min_cbd = float(result[0]) if result[0] is not None else 0.0
            max_cbd = float(result[1]) if result[1] is not None else 20.0

            logger.debug(f"CBD range calculated: {min_cbd}-{max_cbd}%")
            return (min_cbd, max_cbd)

        except Exception as e:
            logger.error(f"Failed to calculate CBD range: {e}")
            return (0.0, 20.0)  # Default fallback

    def get_categories(self) -> List[str]:
        """
        Get available strain categories

        Returns:
            ["Indica", "Sativa", "Hybrid"]
        """
        # Categories are fixed in the schema
        return ["Indica", "Sativa", "Hybrid"]


# Factory function for dependency injection
def get_taxonomy_repository(db_session: Session) -> ITaxonomyRepository:
    """
    Factory function to create taxonomy repository instance

    Args:
        db_session: SQLAlchemy database session

    Returns:
        ITaxonomyRepository instance
    """
    return TaxonomyRepository(db_session)
