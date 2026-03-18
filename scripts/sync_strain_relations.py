#!/usr/bin/env python3
"""
Legacy entrypoint kept for backward compatibility.
Use rebuild_embeddings.py directly for new usage.
"""

from scripts.rebuild_embeddings import rebuild_embeddings


def regenerate_embeddings():
    """Regenerate dual embeddings (EN + ES) for all existing strains."""
    rebuild_embeddings(only_missing=False)


if __name__ == "__main__":
    regenerate_embeddings()
