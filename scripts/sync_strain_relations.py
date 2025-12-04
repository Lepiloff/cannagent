#!/usr/bin/env python3
"""
Legacy entrypoint kept for embedding regeneration.
Full data sync is disabled; we only regenerate embeddings for existing strains.
"""

from app.db.database import SessionLocal
from app.db.repository import StrainRepository
from app.core.rag_service import RAGService
from app.core.llm_interface import get_llm


def regenerate_embeddings():
    """Regenerate dual embeddings (EN + ES) for all existing strains."""
    session = SessionLocal()
    repository = StrainRepository(session)
    rag_service = RAGService(repository, get_llm())

    success_count = 0
    error_count = 0

    try:
        strains = repository.get_strains(limit=10000)
        for idx, strain in enumerate(strains, 1):
            try:
                rag_service.add_strain_embeddings(strain.id)
                success_count += 1
                if idx % 10 == 0:
                    print(f"  🔗 Generated embeddings for {idx} strains...")
            except Exception as e:
                error_count += 1
                print(f"❌ Error generating embedding for '{strain.name}': {e}")
                continue

        print(f"✅ Embedding regeneration completed: {success_count} success, {error_count} errors")
        print("   Each strain now has dual embeddings (embedding_en + embedding_es)")
    finally:
        session.close()


if __name__ == "__main__":
    regenerate_embeddings()
