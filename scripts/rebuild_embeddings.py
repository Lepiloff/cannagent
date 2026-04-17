#!/usr/bin/env python3
"""
Generate multilingual embeddings (EN + ES) for strains in cannamente DB.

Usage (run from canagent-api container):

    # Only strains missing embeddings (default) — e.g. after importing new strains
    python -m scripts.rebuild_embeddings

    # Limit to first N strains without embeddings
    python -m scripts.rebuild_embeddings --limit 100

    # Regenerate ALL strains (e.g. after switching embedding model)
    python -m scripts.rebuild_embeddings --all

    # Clear all embeddings and regenerate from scratch
    python -m scripts.rebuild_embeddings --reset
"""

import argparse
from sqlalchemy import text

from app.db.database import engine, SessionLocal
from app.db.repository import StrainRepository
from app.models.database import Strain as StrainModel
from app.core.rag_service import RAGService
from app.core.llm_interface import get_llm


def has_embedding(value) -> bool:
    """Return True when an embedding vector is present without relying on array truthiness."""
    return value is not None and len(value) > 0


def reset_embeddings() -> None:
    """Clear all existing embeddings."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE strains_strain SET embedding_en = NULL, embedding_es = NULL"))


def get_strains_for_processing(session, only_missing: bool, limit: int | None):
    """
    Get strains to process.

    Args:
        session: DB session
        only_missing: If True, only strains without embeddings
        limit: Max number of strains to process (None = all)
    """
    query = session.query(StrainModel)

    if only_missing:
        query = query.filter(
            (StrainModel.embedding_en == None)
            | (StrainModel.embedding_es == None)
            | (StrainModel.active == False)
        )

    query = query.order_by(StrainModel.id)

    if limit:
        query = query.limit(limit)

    return query.all()


def rebuild_embeddings(only_missing: bool = True, limit: int | None = None) -> None:
    """
    Generate embeddings for strains.

    Args:
        only_missing: If True, skip strains that already have both embeddings
        limit: Max number of strains to process
    """
    session = SessionLocal()
    repository = StrainRepository(session)
    rag_service = RAGService(repository, get_llm())

    success_count = 0
    error_count = 0

    try:
        strains = get_strains_for_processing(session, only_missing, limit)
        total = len(strains)

        mode = "missing only" if only_missing else "all strains"
        print(f"Found {total} strains to process ({mode})")

        if total == 0:
            print("Nothing to do.")
            return

        activated_count = 0

        for idx, strain in enumerate(strains, 1):
            try:
                needs_embeddings = not (
                    has_embedding(strain.embedding_en) and has_embedding(strain.embedding_es)
                )

                if needs_embeddings:
                    generated = rag_service.add_strain_embeddings(strain.id)
                    if not generated:
                        error_count += 1
                        print(f"  Error for '{strain.name}': embedding generation returned False")
                        continue
                    session.refresh(strain)

                success_count += 1

                # Activate strains once both vectors exist, including already-generated ones.
                if (
                    not strain.active
                    and has_embedding(strain.embedding_en)
                    and has_embedding(strain.embedding_es)
                ):
                    strain.active = True
                    session.commit()
                    activated_count += 1

                if idx % 10 == 0:
                    print(f"  Progress: {idx}/{total} strains...")
            except Exception as e:
                error_count += 1
                print(f"  Error for '{strain.name}': {e}")
                continue

        print(f"Done: {success_count} success, {error_count} errors (out of {total})")
        if activated_count:
            print(f"  Activated {activated_count} strains")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dual embeddings (EN + ES) for strains")
    parser.add_argument(
        "--all", action="store_true",
        help="Regenerate embeddings for ALL strains, not just missing ones"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear all existing embeddings before regeneration (implies --all)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max number of strains to process"
    )
    args = parser.parse_args()

    if args.reset:
        print("Clearing existing embeddings...")
        reset_embeddings()
        print("Embeddings cleared.")

    only_missing = not (args.all or args.reset)
    rebuild_embeddings(only_missing=only_missing, limit=args.limit)


if __name__ == "__main__":
    main()
