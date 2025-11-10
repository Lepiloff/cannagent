"""
RAG Service for multilingual embedding generation.
Restores functionality that was removed in Smart Query Executor v3.0.
"""

import structlog
from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.llm_interface import LLMInterface
from app.db.repository import StrainRepository
from app.models.database import Strain as StrainModel

logger = structlog.get_logger()


class RAGService:
    """Service for generating and managing strain embeddings"""

    def __init__(self, repository: StrainRepository, llm: LLMInterface):
        self.repository = repository
        self.llm = llm

    def _build_embedding_text(self, strain: StrainModel, language: str = 'en') -> str:
        """
        Build text for embedding generation based on strain data and language.

        Args:
            strain: Strain model with relations loaded
            language: 'en' or 'es'

        Returns:
            Formatted text for embedding generation
        """
        text_parts = []

        # Strain name and title
        if language == 'en':
            name = getattr(strain, 'name_en', None) or getattr(strain, 'name', '')
            title = getattr(strain, 'title_en', None) or getattr(strain, 'title', '')
            description = getattr(strain, 'description_en', None) or getattr(strain, 'description', '')
        else:  # es
            name = getattr(strain, 'name_es', None) or getattr(strain, 'name', '')
            title = getattr(strain, 'title_es', None) or getattr(strain, 'title', '')
            description = getattr(strain, 'description_es', None) or getattr(strain, 'description', '')

        if name:
            text_parts.append(name)
        if title and title != name:
            text_parts.append(title)

        # Category
        if strain.category:
            text_parts.append(f"Category: {strain.category}")

        # Cannabinoids
        if strain.thc is not None:
            text_parts.append(f"THC: {strain.thc}%")
        if strain.cbd is not None:
            text_parts.append(f"CBD: {strain.cbd}%")
        if strain.cbg is not None:
            text_parts.append(f"CBG: {strain.cbg}%")

        # Effects (Feelings)
        if strain.feelings:
            feeling_names = []
            for feeling in strain.feelings:
                if language == 'en':
                    feeling_name = getattr(feeling, 'name_en', None) or feeling.name
                else:
                    feeling_name = getattr(feeling, 'name_es', None) or feeling.name
                if feeling_name:
                    feeling_names.append(feeling_name)

            if feeling_names:
                text_parts.append(f"Effects: {', '.join(feeling_names)}")

        # Medical benefits (Helps with)
        if strain.helps_with:
            helps_names = []
            for helps in strain.helps_with:
                if language == 'en':
                    helps_name = getattr(helps, 'name_en', None) or helps.name
                else:
                    helps_name = getattr(helps, 'name_es', None) or helps.name
                if helps_name:
                    helps_names.append(helps_name)

            if helps_names:
                text_parts.append(f"Helps with: {', '.join(helps_names)}")

        # Flavors
        if strain.flavors:
            flavor_names = []
            for flavor in strain.flavors:
                if language == 'en':
                    flavor_name = getattr(flavor, 'name_en', None) or flavor.name
                else:
                    flavor_name = getattr(flavor, 'name_es', None) or flavor.name
                if flavor_name:
                    flavor_names.append(flavor_name)

            if flavor_names:
                text_parts.append(f"Flavors: {', '.join(flavor_names)}")

        # Negative effects
        if strain.negatives:
            negative_names = []
            for negative in strain.negatives:
                if language == 'en':
                    negative_name = getattr(negative, 'name_en', None) or negative.name
                else:
                    negative_name = getattr(negative, 'name_es', None) or negative.name
                if negative_name:
                    negative_names.append(negative_name)

            if negative_names:
                text_parts.append(f"Side effects: {', '.join(negative_names)}")

        # Terpenes (scientific names - single language)
        if strain.terpenes:
            terpene_names = [t.name for t in strain.terpenes]
            if terpene_names:
                text_parts.append(f"Terpenes: {', '.join(terpene_names)}")

        # Description (if available and not too long)
        if description:
            # Limit description length to avoid token overload
            description_preview = description[:500] if len(description) > 500 else description
            text_parts.append(description_preview)

        return " ".join(text_parts)

    def generate_embedding(self, strain: StrainModel, language: str = 'en') -> Optional[List[float]]:
        """
        Generate embedding for a strain in specified language.

        Args:
            strain: Strain model with relations loaded
            language: 'en' or 'es'

        Returns:
            Embedding vector or None if generation fails
        """
        try:
            # Build text for embedding
            embedding_text = self._build_embedding_text(strain, language)

            if not embedding_text:
                logger.warning(
                    f"Empty embedding text for strain {strain.id} ({language})"
                )
                return None

            # Generate embedding via LLM
            embedding = self.llm.generate_embedding(embedding_text)

            logger.debug(
                f"Generated {language} embedding for strain",
                strain_id=strain.id,
                strain_name=strain.name,
                text_length=len(embedding_text),
                embedding_dim=len(embedding)
            )

            return embedding

        except Exception as e:
            logger.error(
                f"Failed to generate {language} embedding",
                strain_id=strain.id,
                error=str(e)
            )
            return None

    def add_strain_embeddings(self, strain_id: int) -> bool:
        """
        Generate and save dual embeddings (EN + ES) for a strain.

        Args:
            strain_id: ID of the strain to process

        Returns:
            True if successful, False otherwise
        """
        try:
            # Load strain with all relations
            strain = self.repository.get_strain_by_id(strain_id)

            if not strain:
                logger.error(f"Strain not found: {strain_id}")
                return False

            # Generate EN embedding
            embedding_en = self.generate_embedding(strain, language='en')

            # Generate ES embedding
            embedding_es = self.generate_embedding(strain, language='es')

            if not embedding_en and not embedding_es:
                logger.warning(
                    f"Failed to generate both embeddings for strain {strain_id}"
                )
                return False

            # Update strain with embeddings
            if embedding_en:
                strain.embedding_en = embedding_en

            if embedding_es:
                strain.embedding_es = embedding_es

            # Commit changes
            self.repository.db.commit()

            logger.info(
                f"Successfully generated embeddings for strain",
                strain_id=strain_id,
                strain_name=strain.name,
                has_en=bool(embedding_en),
                has_es=bool(embedding_es)
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to add embeddings for strain {strain_id}",
                error=str(e)
            )
            self.repository.db.rollback()
            return False

    def regenerate_all_embeddings(self, batch_size: int = 10) -> dict:
        """
        Regenerate embeddings for all active strains.

        Args:
            batch_size: Number of strains to process before commit

        Returns:
            Statistics dictionary with success/failure counts
        """
        stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }

        try:
            # Get all active strains
            strains = self.repository.get_strains(limit=10000)  # Process all
            stats['total'] = len(strains)

            logger.info(f"Starting embedding generation for {stats['total']} strains")

            processed = 0
            for strain in strains:
                try:
                    success = self.add_strain_embeddings(strain.id)

                    if success:
                        stats['success'] += 1
                    else:
                        stats['failed'] += 1

                    processed += 1

                    # Commit in batches to avoid memory issues
                    if processed % batch_size == 0:
                        self.repository.db.commit()
                        logger.info(
                            f"Progress: {processed}/{stats['total']} strains processed"
                        )

                except Exception as e:
                    stats['failed'] += 1
                    logger.error(
                        f"Error processing strain {strain.id}",
                        error=str(e)
                    )
                    continue

            # Final commit
            self.repository.db.commit()

            logger.info(
                "Embedding generation complete",
                **stats
            )

            return stats

        except Exception as e:
            logger.error(
                "Failed to regenerate embeddings",
                error=str(e)
            )
            self.repository.db.rollback()
            return stats
