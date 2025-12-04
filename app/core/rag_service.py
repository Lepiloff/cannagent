import os
from typing import List, Optional

from sqlalchemy.orm import joinedload

from app.db.database import SessionLocal
from app.db.repository import StrainRepository
from app.models.database import Strain as StrainModel
from app.core.llm_interface import get_llm


class RAGService:
    """
    Minimal embedding service for legacy sync scripts.
    Generates and stores multilingual embeddings (en/es) for strains.
    """

    def __init__(self, repository: Optional[StrainRepository] = None, llm=None):
        self.session = SessionLocal()
        self.repository = repository or StrainRepository(self.session)
        self.llm = llm or get_llm()

    def _localize(self, value_en: Optional[str], value_es: Optional[str], language: str) -> Optional[str]:
        if language == "es":
            return value_es or value_en
        return value_en or value_es

    def _build_embedding_text(self, strain: StrainModel, language: str) -> str:
        parts: List[str] = []

        parts.append(self._localize(strain.title_en, strain.title_es, language) or strain.name)
        parts.append(self._localize(strain.description_en, strain.description_es, language) or strain.description)
        parts.append(self._localize(strain.text_content_en, strain.text_content_es, language))
        parts.append(self._localize(strain.keywords_en, strain.keywords_es, language))

        # Relationships
        def names(items, attr_en="name_en", attr_es="name_es", fallback="name"):
            out = []
            for item in items or []:
                name_en = getattr(item, attr_en, None)
                name_es = getattr(item, attr_es, None)
                out.append(self._localize(name_en, name_es, language) or getattr(item, fallback, None))
            return [n for n in out if n]

        feelings = names(strain.feelings)
        helps = names(strain.helps_with)
        negatives = names(strain.negatives)
        flavors = names(strain.flavors)
        terpenes = [t.name for t in (strain.terpenes or []) if t.name]

        if feelings:
            parts.append("feelings: " + ", ".join(feelings))
        if helps:
            parts.append("helps_with: " + ", ".join(helps))
        if negatives:
            parts.append("negatives: " + ", ".join(negatives))
        if flavors:
            parts.append("flavors: " + ", ".join(flavors))
        if terpenes:
            parts.append("terpenes: " + ", ".join(terpenes))

        return " | ".join([p for p in parts if p])

    def _load_strain(self, strain_id: int) -> Optional[StrainModel]:
        return (
            self.repository.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .options(joinedload(StrainModel.terpenes))
            .filter(StrainModel.id == strain_id)
            .first()
        )

    def add_strain_embeddings(self, strain_id: int) -> Optional[StrainModel]:
        """Generate and store embeddings for both languages for a given strain."""
        strain = self._load_strain(strain_id)
        if not strain:
            return None

        # English
        text_en = self._build_embedding_text(strain, "en")
        if text_en:
            embedding_en = self.llm.generate_embedding(text_en)
            self.repository.update_strain_embedding(strain.id, embedding_en, language="en")

        # Spanish
        text_es = self._build_embedding_text(strain, "es")
        if text_es:
            embedding_es = self.llm.generate_embedding(text_es)
            self.repository.update_strain_embedding(strain.id, embedding_es, language="es")

        return strain

    def generate_embedding(self, strain: StrainModel, language: str = "en") -> List[float]:
        """Generate a single-language embedding for compatibility."""
        text = self._build_embedding_text(strain, language)
        return self.llm.generate_embedding(text) if text else []

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass


__all__ = ["RAGService"]
