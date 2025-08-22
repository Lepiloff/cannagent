"""Intent types for strain recommendations (cleaned for Smart Query Executor v3.0)."""

from enum import Enum


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