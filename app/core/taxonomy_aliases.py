"""Canonical taxonomy aliases shared by canna read/write paths.

These aliases mirror the Django taxonomy cleanup rules so this service does
not recreate legacy duplicate rows when updating strain relationships.
"""

import unicodedata


TAXONOMY_NAME_ALIASES = {
    "Negative": {
        "anxiety": "Anxious",
        "ansiedad": "Anxious",
    },
    "HelpsWith": {
        "inflamacion": "Inflamación",
        "presion ocular": "Presión ocular",
    },
    "Terpene": {
        "cariofileno": "Caryophyllene",
        "cariofileno (picante)": "Caryophyllene",
        "humuleno": "Humulene",
        "humuleno (terroso)": "Humulene",
        "limoneno": "Limonene",
        "limoneno (citrus)": "Limonene",
        "limoneno (cítrico)": "Limonene",
        "linalool (floral)": "Linalool",
        "mirceno": "Myrcene",
        "mirceno (herbal)": "Myrcene",
        "ocimeno": "Ocimene",
        "ocimeno (dulce)": "Ocimene",
        "ocimeno (floral)": "Ocimene",
        "pineno": "Pinene",
        "pineno (amaderado)": "Pinene",
        "pineno (woody)": "Pinene",
        "terpinoleno": "Terpinolene",
        "terpinoleno (floral)": "Terpinolene",
    },
}


def normalize_taxonomy_name(name: str) -> str:
    """Normalize user/imported taxonomy text for alias lookup."""
    normalized = unicodedata.normalize("NFC", str(name or "")).strip()
    return " ".join(normalized.split())


def canonical_taxonomy_name(model_name: str, name: str) -> str:
    """Return canonical DB name for a taxonomy value when an alias is known."""
    normalized = normalize_taxonomy_name(name)
    aliases = TAXONOMY_NAME_ALIASES.get(model_name, {})
    return aliases.get(normalized.lower(), normalized)
