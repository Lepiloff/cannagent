"""Input sanitization and prompt injection detection.

Provides:
- sanitize_input: unicode normalization + zero-width character removal
- detect_prompt_injection: heuristic regex-based PI signal detection
- check_output_leakage: checks LLM output for system prompt leakage
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

# Zero-width and invisible Unicode characters
_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\u2060\uFEFF\u00AD\u2028\u2029]")


def sanitize_input(text: str) -> str:
    """Normalize and clean user input.

    - NFKC normalization (collapses compatibility characters)
    - Removes zero-width / invisible characters
    - Strips leading/trailing whitespace
    """
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = text.strip()
    return text


# ---------------------------------------------------------------------------
# Prompt injection detection (heuristic, regex-based)
# ---------------------------------------------------------------------------

# Patterns that signal a prompt injection attempt.
# Compiled with IGNORECASE. Order doesn't matter — any match triggers the flag.
_PI_PATTERNS = [
    # EN: instruction override attempts
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions|rules|prompts?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions|rules)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions|rules)", re.IGNORECASE),
    # EN: system prompt extraction
    re.compile(r"(show|reveal|print|output|display|repeat|give)\s+(me\s+)?(?:your|the\s+)?system\s+(prompt|instructions|rules)", re.IGNORECASE),
    re.compile(r"(show|reveal|print|output|display|repeat|give)\s+(me\s+)?your\s+(prompt|instructions|rules)", re.IGNORECASE),
    re.compile(r"what\s+(are|is)\s+your\s+system\s+(prompt|instructions|rules|guidelines)", re.IGNORECASE),
    re.compile(r"what\s+(are|is)\s+your\s+(prompt|instructions|guidelines)\b", re.IGNORECASE),
    # EN: role hijacking
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?(?!a?\s*budtender\b)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+", re.IGNORECASE),
    re.compile(r"(DAN|developer)\s+mode", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    # ES: instruction override attempts
    re.compile(r"ignora\s+(todas?\s+)?(las\s+)?(instrucciones|reglas|anteriores)", re.IGNORECASE),
    re.compile(r"olvida\s+(todas?\s+)?(las\s+)?(instrucciones|reglas)", re.IGNORECASE),
    # ES: system prompt extraction
    re.compile(r"(muestra|revela|dime|muéstrame)\s+(el\s+|las?\s+)?(prompt|instrucciones|reglas)\s+(del\s+sistema)?", re.IGNORECASE),
    re.compile(r"(cu[aá]les?\s+son|qu[eé]\s+son)\s+(tus|las)\s+(instrucciones|reglas)", re.IGNORECASE),
    # ES: role hijacking
    re.compile(r"ahora\s+eres\s+", re.IGNORECASE),
    re.compile(r"act[uú]a\s+como\s+(?!(un\s+)?budtender\b)", re.IGNORECASE),
    # Universal: structural markers that shouldn't appear in normal user input
    re.compile(r"```system", re.IGNORECASE),
    re.compile(r"\[SYSTEM\]", re.IGNORECASE),
    re.compile(r"<<SYS>>", re.IGNORECASE),
    re.compile(r"###\s*Instruction", re.IGNORECASE),
]


def detect_prompt_injection(text: str) -> bool:
    """Check user input for prompt injection signals.

    Returns True if any heuristic pattern matches.
    Logs the event for observability.
    """
    for pattern in _PI_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "Prompt injection signal detected",
                extra={
                    "pi_signal": True,
                    "pattern": pattern.pattern,
                    "message_preview": text[:120],
                },
            )
            return True
    return False


# ---------------------------------------------------------------------------
# Output leakage detection
# ---------------------------------------------------------------------------

# Signature phrases from the system prompt that should never appear in output.
# Keep this list short — only unique/distinctive fragments.
_SYSTEM_PROMPT_SIGNATURES = [
    # Technical prompt structure — never in a normal cannabis response
    "query intent detection (critical",
    "specific strain query detection (critical",
    "is_search_query = false",
    "is_search_query = true",
    "exact attribute extraction (for sql pre-filtering",
    "follow-up detection rules",
    "thc level detection (for sql",
    "cbd level detection (for sql",
    "natural_response",
    "suggested_follow_ups",
]


def check_output_leakage(text: str) -> bool:
    """Check if LLM output contains fragments of the system prompt.

    Returns True if leakage detected — caller should replace with fallback.
    """
    lower = text.lower()
    for sig in _SYSTEM_PROMPT_SIGNATURES:
        if sig in lower:
            logger.warning(
                "System prompt leakage detected in output",
                extra={"leaked_signature": sig},
            )
            return True
    return False


def get_output_leakage_guard_chars() -> int:
    """Number of trailing characters to retain for cross-chunk leakage checks."""
    if not _SYSTEM_PROMPT_SIGNATURES:
        return 0
    return max(len(sig) for sig in _SYSTEM_PROMPT_SIGNATURES) - 1
