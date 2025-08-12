"""Intent detection and categorization for strain recommendations."""

from typing import Dict, List, Set, Optional
from enum import Enum

class EnergyType(Enum):
    """Energy types for feelings categorization."""
    ENERGIZING = "energizing"
    RELAXING = "relaxing" 
    NEUTRAL = "neutral"

class IntentType(Enum):
    """User intent types for strain recommendations."""
    SLEEP = "sleep"
    RELAXATION = "relaxation"
    ENERGY = "energy"
    FOCUS = "focus"
    CREATIVITY = "creativity"
    PAIN_RELIEF = "pain_relief"
    ANXIETY_RELIEF = "anxiety_relief"
    MOOD_ENHANCEMENT = "mood_enhancement"
    GENERAL = "general"

# Feelings categorized by energy type
FEELINGS_BY_ENERGY = {
    EnergyType.ENERGIZING: {
        "Energetic", "Creative", "Focused", "Talkative", 
        "Uplifted", "Euphoric"
    },
    EnergyType.RELAXING: {
        "Sleepy", "Relaxed", "Hungry"
    },
    EnergyType.NEUTRAL: {
        "Happy", "Giggly", "Tingly", "Aroused"
    }
}

# Intent detection rules
INTENT_RULES = {
    IntentType.SLEEP: {
        "keywords": {
            "sleep", "sleepy", "insomnia", "rest", "bedtime", "night", 
            "tired", "drowsy", "slumber", "dormir", "sueño", "descanso"
        },
        "required_feelings": {"Sleepy", "Relaxed", "Hungry"},  # Any of these is good
        "preferred_categories": {"Indica", "Hybrid"},  # Include Hybrid for better variety
        "exclude_feelings": {"Energetic", "Focused", "Talkative", "Uplifted"},
        "required_helps_with": {"Insomnia", "Stress"},  # Bonus if helps with these
        "exclude_helps_with": set()
    },
    
    IntentType.RELAXATION: {
        "keywords": {
            "relax", "relaxation", "chill", "calm", "unwind", "stress", 
            "tension", "relajar", "calma", "tranquilo"
        },
        "required_feelings": {"Relaxed"},
        "preferred_categories": {"Indica", "Hybrid"},
        "exclude_feelings": {"Energetic", "Talkative"},
        "required_helps_with": {"Stress", "Anxiety"},
        "exclude_helps_with": set()
    },
    
    IntentType.ENERGY: {
        "keywords": {
            "energy", "energetic", "active", "wake up", "morning", "daytime",
            "boost", "vigorous", "energía", "activo", "despertar"
        },
        "required_feelings": {"Energetic", "Uplifted"},
        "preferred_categories": {"Sativa", "Hybrid"},  # Include energizing Hybrids
        "exclude_feelings": {"Sleepy", "Relaxed"},
        "required_helps_with": {"Fatigue"},
        "exclude_helps_with": {"Insomnia"}
    },
    
    IntentType.FOCUS: {
        "keywords": {
            "focus", "concentrate", "work", "study", "productivity", "clear mind",
            "attention", "concentrar", "trabajar", "estudiar"
        },
        "required_feelings": {"Focused", "Creative"},
        "preferred_categories": {"Sativa", "Hybrid"},
        "exclude_feelings": {"Sleepy", "Giggly"},
        "required_helps_with": set(),
        "exclude_helps_with": {"Insomnia"}
    },
    
    IntentType.CREATIVITY: {
        "keywords": {
            "creative", "creativity", "art", "music", "inspiration", "ideas",
            "imagination", "creativo", "arte", "música", "inspiración"
        },
        "required_feelings": {"Creative", "Euphoric", "Uplifted"},
        "preferred_categories": {"Sativa", "Hybrid"},
        "exclude_feelings": {"Sleepy"},
        "required_helps_with": set(),
        "exclude_helps_with": {"Insomnia"}
    },
    
    IntentType.PAIN_RELIEF: {
        "keywords": {
            "pain", "ache", "hurt", "chronic", "headache", "migraine",
            "arthritis", "muscle", "dolor", "duele", "crónico"
        },
        "required_feelings": set(),
        "preferred_categories": {"Indica", "Hybrid"},
        "exclude_feelings": set(),
        "required_helps_with": {"Pain", "Headaches"},
        "exclude_helps_with": set()
    },
    
    IntentType.ANXIETY_RELIEF: {
        "keywords": {
            "anxiety", "anxious", "nervous", "worry", "panic", "stress",
            "calm", "ansiedad", "nervioso", "preocupado"
        },
        "required_feelings": {"Relaxed", "Happy"},
        "preferred_categories": {"Indica", "Hybrid"},
        "exclude_feelings": {"Anxious", "Paranoid"},
        "required_helps_with": {"Anxiety", "Stress"},
        "exclude_helps_with": set()
    },
    
    IntentType.MOOD_ENHANCEMENT: {
        "keywords": {
            "happy", "mood", "depression", "sad", "uplift", "joy",
            "cheerful", "feliz", "humor", "depresión", "triste"
        },
        "required_feelings": {"Happy", "Euphoric", "Uplifted", "Giggly"},
        "preferred_categories": {"Sativa", "Hybrid"},
        "exclude_feelings": set(),
        "required_helps_with": {"Depression"},
        "exclude_helps_with": set()
    }
}

class IntentDetector:
    """Detects user intent from natural language queries."""
    
    def detect_intent(self, query: str) -> IntentType:
        """
        Detect primary intent from user query.
        
        Args:
            query: User's natural language query
            
        Returns:
            Detected intent type
        """
        query_lower = query.lower()
        intent_scores = {}
        
        # Score each intent based on keyword matches
        for intent_type, rules in INTENT_RULES.items():
            score = 0
            for keyword in rules["keywords"]:
                if keyword in query_lower:
                    score += 1
            
            # Boost score for exact matches
            for keyword in rules["keywords"]:
                if keyword == query_lower.strip():
                    score += 3
                    
            intent_scores[intent_type] = score
        
        # Return intent with highest score, default to GENERAL
        if not intent_scores or max(intent_scores.values()) == 0:
            return IntentType.GENERAL
            
        return max(intent_scores, key=intent_scores.get)
    
    def get_intent_filters(self, intent: IntentType) -> Dict:
        """
        Get filtering rules for a specific intent.
        
        Args:
            intent: The detected intent
            
        Returns:
            Dictionary with filtering rules
        """
        default_filters = {
            "required_feelings": set(),
            "preferred_categories": set(),
            "exclude_feelings": set(),
            "required_helps_with": set(),
            "exclude_helps_with": set()
        }
        
        if intent == IntentType.GENERAL:
            return default_filters
            
        return INTENT_RULES.get(intent, default_filters)

def get_energy_type(feeling: str) -> Optional[EnergyType]:
    """Get energy type for a specific feeling."""
    for energy_type, feelings in FEELINGS_BY_ENERGY.items():
        if feeling in feelings:
            return energy_type
    return None

def is_conflicting_intent(intent1: IntentType, intent2: IntentType) -> bool:
    """Check if two intents conflict with each other."""
    conflicting_pairs = {
        (IntentType.SLEEP, IntentType.ENERGY),
        (IntentType.SLEEP, IntentType.FOCUS),
        (IntentType.SLEEP, IntentType.CREATIVITY),
        (IntentType.RELAXATION, IntentType.ENERGY),
    }
    
    return (intent1, intent2) in conflicting_pairs or (intent2, intent1) in conflicting_pairs