from typing import Dict, Any, List, Optional, Set
from app.models.session import ConversationSession
from app.models.schemas import Strain
from app.core.taxonomy import normalize_list
import os


SPANISH_HINT_WORDS = {
    "para", "necesito", "quiero", "cuál", "qué", "más", "mejor",
    "variedad", "cepa", "dormir", "energía", "ansiedad", "dolor"
}


EFFECT_SYNONYMS = {
    "sleep": {"sleep", "sleepy", "relax", "relaxed", "insomnia"},
    "energy": {"energy", "energetic", "uplifted"},
    "creativity": {"creative", "creativity"},
    "focus": {"focus", "focused"},
    "anxiety": {"anxiety", "anxious", "calm"},
    "pain": {"pain", "pain relief"}
}


CATEGORY_WORDS = {
    "indica": "Indica",
    "índica": "Indica",
    "sativa": "Sativa",
    "satíva": "Sativa",
    "hybrid": "Hybrid",
    "híbrida": "Hybrid",
}


FLAVOR_WORDS = {
    "menthol": "menthol",
    "mint": "menthol",
    "citrus": "citrus",
    "pine": "pine",
    "diesel": "diesel",
}


# Medical keywords → canonical helps_with
MEDICAL_WORDS = {
    "insomnia": "insomnia",
    "sleep": "insomnia",
    "ansiedad": "anxiety",
    "anxiety": "anxiety",
    "estres": "stress",
    "estrés": "stress",
    "stress": "stress",
    "depresion": "depression",
    "depresión": "depression",
    "depression": "depression",
    "dolor": "pain",
    "pain": "pain",
    "nausea": "nausea",
    "nauseas": "nausea",
    "inflamacion": "inflammation",
    "inflamación": "inflammation",
}


def detect_language(text: str) -> str:
    tl = text.lower()
    count = sum(1 for w in SPANISH_HINT_WORDS if w in tl)
    # Требуем хотя бы 2 индикатора для испанского, иначе en
    return 'es' if count >= 2 else 'en'


def extract_request_signals(text: str) -> Dict[str, Any]:
    tl = text.lower()

    requested_category: Optional[str] = None
    for k, v in CATEGORY_WORDS.items():
        if k in tl:
            requested_category = v
            break

    desired_effects: Set[str] = set()
    avoid_effects: Set[str] = set()
    if any(w in tl for w in EFFECT_SYNONYMS["creativity"]):
        desired_effects.add("Creative")
    if any(w in tl for w in EFFECT_SYNONYMS["sleep"]):
        desired_effects.update({"Sleepy", "Relaxed"})
        avoid_effects.update({"Energetic", "Uplifted"})
    if any(w in tl for w in EFFECT_SYNONYMS["energy"]):
        desired_effects.update({"Energetic", "Uplifted"})
        avoid_effects.update({"Sleepy", "Relaxed"})
    if any(w in tl for w in EFFECT_SYNONYMS["focus"]):
        desired_effects.add("Focused")
    if any(w in tl for w in EFFECT_SYNONYMS["anxiety"]):
        avoid_effects.update({"Paranoid", "Anxious"})

    flavors: Set[str] = set()
    for k, v in FLAVOR_WORDS.items():
        if k in tl:
            flavors.add(v)

    medicals: Set[str] = set()
    for k, v in MEDICAL_WORDS.items():
        if k in tl:
            medicals.add(v)

    sort_request: Optional[str] = None
    if any(w in tl for w in ["highest thc", "most thc", "strongest", "from highest to lowest"]):
        sort_request = "thc_desc"
    elif any(w in tl for w in ["lowest thc", "least thc", "mildest", "from lowest to highest"]):
        sort_request = "thc_asc"

    reset_indicator = any(w in tl for w in ["start over", "reset", "new search", "nueva consulta", "empezar de nuevo"])

    language = detect_language(text)

    return {
        "requested_category": requested_category,
        "desired_effects": sorted(desired_effects),
        "avoid_effects": sorted(avoid_effects),
        "flavors": sorted(flavors),
        "medical": sorted(medicals),
        "sort_request": sort_request,
        "reset_indicator": reset_indicator,
        "language": language,
    }


def _session_categories(strains: List[Strain]) -> Set[str]:
    # Приводим к str и фильтруем None для строгой типизации
    return {str(s.category) for s in strains if getattr(s, 'category', None)}


def evaluate_context_match(session_strains: List[Strain], signals: Dict[str, Any]) -> Dict[str, Any]:
    if not session_strains:
        return {
            "has_context": False,
            "category_match": False,
            "effects_match": 0.0,
            "flavors_match": 0.0,
        }

    categories = _session_categories(session_strains)
    category_match = (signals.get("requested_category") in categories) if signals.get("requested_category") else True

    # Effects match: средняя доля пересечений
    desired = set(signals.get("desired_effects") or [])
    flavor_targets = set(signals.get("flavors") or [])

    if desired:
        effect_hits = 0
        for s in session_strains:
            strain_effects = {f.name.lower() for f in (s.feelings or [])}
            if strain_effects & {d.lower() for d in desired}:
                effect_hits += 1
        effects_match = effect_hits / max(len(session_strains), 1)
    else:
        effects_match = 1.0

    if flavor_targets:
        flavor_hits = 0
        for s in session_strains:
            strain_flavors = {fl.name.lower() for fl in (s.flavors or [])}
            if strain_flavors & {f.lower() for f in flavor_targets}:
                flavor_hits += 1
        flavors_match = flavor_hits / max(len(session_strains), 1)
    else:
        flavors_match = 1.0

    # Медицинские соответствия
    medical_targets = set(signals.get("medical") or [])
    if medical_targets:
        med_hits = 0
        for s in session_strains:
            vals = normalize_list("helps_with", [h.name for h in (s.helps_with or [])])
            if set(vals) & medical_targets:
                med_hits += 1
        medical_match = med_hits / max(len(session_strains), 1)
    else:
        medical_match = 1.0

    return {
        "has_context": True,
        "category_match": category_match,
        "effects_match": effects_match,
        "flavors_match": flavors_match,
        "medical_match": medical_match,
    }


def decide_action_hint(session: ConversationSession, session_strains: List[Strain], signals: Dict[str, Any]) -> Dict[str, Any]:
    match = evaluate_context_match(session_strains, signals)

    force_expand = False
    # Если запрошена новая категория и она не совпадает с текущими контекстными сортами → расширять поиск
    category_strict = os.getenv("CATEGORY_MATCH_STRICT", "true").lower() == "true"
    if category_strict and signals.get("requested_category") and not match.get("category_match", True):
        force_expand = True

    # Если запрошены эффекты/вкусы и контекст покрывает их слабо (<0.5) → расширять поиск
    eff_thr = float(os.getenv("EFFECTS_MATCH_THRESHOLD", "0.5"))
    flv_thr = float(os.getenv("FLAVORS_MATCH_THRESHOLD", "0.5"))
    if ((signals.get("desired_effects") and match.get("effects_match", 1.0) < eff_thr) or
        (signals.get("flavors") and match.get("flavors_match", 1.0) < flv_thr)):
        force_expand = True

    # Если запрошены медицинские показания и контекст покрывает слабо (<0.5) → расширять поиск
    med_thr = float(os.getenv("MEDICAL_MATCH_THRESHOLD", "0.5"))
    if (signals.get("medical") and match.get("medical_match", 1.0) < med_thr):
        force_expand = True

    filters: Dict[str, Any] = {}
    if signals.get("requested_category"):
        filters["category"] = {"operator": "eq", "value": signals["requested_category"], "priority": 2}
    if signals.get("desired_effects"):
        filters["effects"] = {"operator": "contains", "values": signals["desired_effects"], "priority": 1}
    if signals.get("avoid_effects"):
        # Дополнительный ключ для исключений эффектов; будет нормализован на уровне executor
        filters["effects_exclude"] = {"operator": "not_contains", "values": signals["avoid_effects"], "priority": 1}
    if signals.get("flavors"):
        filters["flavors"] = {"operator": "contains", "values": signals["flavors"], "priority": 3}
    if signals.get("medical"):
        filters["helps_with"] = {"operator": "contains", "values": signals["medical"], "priority": 1}

    sort_cfg: Optional[Dict[str, Any]] = None
    if signals.get("sort_request") == "thc_desc":
        sort_cfg = {"field": "thc", "order": "desc"}
    elif signals.get("sort_request") == "thc_asc":
        sort_cfg = {"field": "thc", "order": "asc"}

    return {
        "force_expand_search": force_expand,
        "suggested_filters": filters,
        "suggested_sort": sort_cfg,
        "language": signals.get("language", "en")
    }


