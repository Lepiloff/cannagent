#!/usr/bin/env python3
"""Utility for resetting and regenerating multilingual embeddings in cannamente DB."""

import argparse
from sqlalchemy import text

from app.db.database import engine
from scripts.sync_strain_relations import regenerate_embeddings


def reset_embeddings() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE strains_strain SET embedding_en = NULL, embedding_es = NULL"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and regenerate dual embeddings")
    parser.add_argument("--reset", action="store_true", help="Clear existing embeddings before regeneration")
    args = parser.parse_args()

    if args.reset:
        print("Clearing existing embeddings...")
        reset_embeddings()
        print("Embeddings cleared")

    print("Regenerating dual embeddings...")
    regenerate_embeddings()
    print("Embedding regeneration complete")


if __name__ == "__main__":
    main()
