from typing import List, Dict
import unicodedata


def _norm(text: str) -> str:
    if text is None:
        return ""
    t = str(text).strip().lower()
    # remove accents
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    # lightweight cleanup
    t = t.replace("/", " ").replace("_", " ").replace("-", " ")
    t = " ".join(t.split())
    return t


# Canonical tokens (English) with multilingual synonyms
_SYNONYMS: Dict[str, Dict[str, List[str]]] = {
    "flavors": {
        "mint": ["menthol", "mint", "minty", "peppermint", "spearmint", "menta", "mentol", "mentolado"],
        "citrus": ["citrus", "lemon", "lime", "orange", "grapefruit", "tangerine", "mandarin", "citricos", "citrico", "naranja", "limon", "lima"],
        "pepper": ["pepper", "peppery", "black pepper", "pimienta"],
        "woody": ["woody", "wood", "woodsy", "forest", "cedar", "oak", "madera"],
        "pine": ["pine", "piny", "pino", "resin"],
        "earthy": ["earthy", "earth", "soil", "dirt", "terroso"],
        "diesel": ["diesel", "gas", "gassy", "fuel", "petrol", "chemical", "chem"],
        "sweet": ["sweet", "sugary", "candy", "dulce"],
        "vanilla": ["vanilla", "creamy", "cream", "butter", "buttery"],
        "berry": ["berry", "berries", "strawberry", "blueberry", "raspberry", "blackberry", "fresa", "arandano"],
        "grape": ["grape", "grapey", "wine", "uva"],
        "tropical": ["tropical", "mango", "pineapple", "banana", "papaya", "guava"],
        "chocolate": ["chocolate", "cocoa", "cacao"],
        "coffee": ["coffee", "espresso", "cafe"],
        "cheese": ["cheese", "cheesy", "queso"],
        "skunk": ["skunk", "skunky"],
        "spicy/herbal": ["spicy", "herbal", "spice", "hierbas", "especiado"],
        "fruity": ["fruit", "fruity", "fruta"],
        "floral": ["floral", "flower", "rose", "roses", "flor"],
    },
    "effects": {
        "relaxed": ["relaxed", "calm", "soothing", "chill", "tranquil", "relajacion", "relajado"],
        "uplifted": ["uplifted", "elevated", "elevado", "subidon"],
        "happy": ["happy", "euphoric", "euphoria", "feliz", "euforico"],
        "energetic": ["energetic", "energizing", "energy", "energico"],
        "creative": ["creative", "inspired", "creativo"],
        "focused": ["focused", "focus", "concentrated", "concentrado"],
        "sleepy": ["sleepy", "drowsy", "sedated", "couch lock", "somnoliento"],
        "hungry": ["hungry", "munchies", "appetite", "hambriento"],
        "talkative": ["talkative", "chatty", "sociable", "hablador"],
        "giggly": ["giggly", "laughing", "risueno", "risueño"],
        "aroused": ["aroused", "libido", "excitado"],
        "tingly": ["tingly", "buzzing", "cosquilleo"],
    },
    "negatives": {
        "dry eyes": ["dry eyes", "red eyes", "ojos secos", "ojos rojos"],
        "dizzy": ["dizzy", "mareado"],
        "anxious": ["anxious", "anxiety", "ansioso", "ansiedad"],
        "paranoid": ["paranoid", "paranoia", "paranoico"],
        "headache": ["headache", "migraine", "dolor de cabeza", "migraña"],
        "fatigue": ["fatigue", "tired", "cansancio", "fatiga"],
        "dry mouth": ["dry mouth", "cottonmouth", "boca seca"],
    },
    "helps_with": {
        "anxiety": ["anxiety", "ansiedad"],
        "stress": ["stress", "estres", "estrés"],
        "depression": ["depression", "depresion", "depresión"],
        "insomnia": ["insomnia", "sleep", "insomnio"],
        "pain": ["pain", "dolor"],
        "nausea": ["nausea", "nauseous", "nauseas", "nauseas"],
        "inflammation": ["inflammation", "inflamacion", "inflamación"],
        "appetite": ["appetite", "appetite loss", "apetito", "perdida de apetito"],
        "ptsd": ["ptsd", "post traumatic stress", "trastorno de estres postraumatico"],
        "adhd": ["adhd", "attention", "deficit de atencion"],
        "headache": ["headache", "migraine", "migraña", "dolor de cabeza"],
        "cramps": ["cramps", "calambres"],
    },
}


def normalize_token(category: str, token: str) -> str:
    """Return canonical form when known, otherwise normalized lowercase token without accents."""
    cat = _SYNONYMS.get(category, {})
    t = _norm(token)
    for canonical, syns in cat.items():
        if t == _norm(canonical) or t in (_norm(s) for s in syns):
            return canonical
    return t


def normalize_list(category: str, tokens: List[str]) -> List[str]:
    if not tokens:
        return []
    normalized = [normalize_token(category, t) for t in tokens]
    # preserve order, dedupe
    seen = set()
    result: List[str] = []
    for t in normalized:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def get_synonyms(category: str, token: str) -> List[str]:
    """Return synonyms (normalized) including the canonical token itself."""
    cat = _SYNONYMS.get(category, {})
    t = _norm(token)
    for canonical, syns in cat.items():
        if t == _norm(canonical) or t in (_norm(s) for s in syns):
            return [canonical] + [normalize_token(category, s) for s in syns]
    return [t]


