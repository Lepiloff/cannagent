"""
LLM Provider Registry — provides LLM instances by purpose.

Supports per-purpose provider configuration via env vars:
    ANALYSIS_LLM_PROVIDER / ANALYSIS_LLM_MODEL
    RESPONSE_LLM_PROVIDER / RESPONSE_LLM_MODEL
    EMBEDDING_MODEL (existing)

Falls back to single-provider mode when only OPENAI_API_KEY is set.
"""

import logging
import os
from typing import Optional

from app.core.llm_interface import (
    AnalysisProvider,
    EmbeddingProvider,
    LLMInterface,
    ResponseProvider,
    get_llm,
)
from app.core.prompt_strategy import PromptStrategy, OpenAIPromptStrategy, GroqPromptStrategy

logger = logging.getLogger(__name__)


class LLMRegistry:
    """Central registry that provides LLM instances by purpose.

    Default: all three capabilities are served by a single OpenAILLM
    (backward compatible with existing get_llm() behavior).

    Per-purpose override via env vars:
      ANALYSIS_LLM_PROVIDER=groq  +  GROQ_API_KEY  +  GROQ_ANALYSIS_MODEL (optional)
    """

    def __init__(self):
        self._default: Optional[LLMInterface] = None
        self._analysis: Optional[AnalysisProvider] = None
        self._response: Optional[ResponseProvider] = None
        self._embedding: Optional[EmbeddingProvider] = None
        self._prompt_strategy: Optional[PromptStrategy] = None
        self._init_from_env()

    def _init_from_env(self) -> None:
        """Initialize per-purpose providers from environment variables."""
        analysis_provider = os.getenv('ANALYSIS_LLM_PROVIDER', '').lower()
        response_provider = os.getenv('RESPONSE_LLM_PROVIDER', '').lower()

        # --- Analysis provider ---
        if analysis_provider == 'groq':
            groq_api_key = os.getenv('GROQ_API_KEY')
            if not groq_api_key:
                logger.warning("ANALYSIS_LLM_PROVIDER=groq but GROQ_API_KEY not set — falling back to OpenAI")
            else:
                try:
                    from app.core.llm_interface import GroqLLM
                    self._analysis = GroqLLM(groq_api_key)
                    self._prompt_strategy = GroqPromptStrategy()
                    logger.info(f"Analysis provider: Groq ({os.getenv('GROQ_ANALYSIS_MODEL', 'llama-3.3-70b-versatile')})")
                except ImportError as e:
                    logger.warning(f"Failed to load GroqLLM ({e}) — falling back to OpenAI")

        # --- Response provider ---
        # Currently only OpenAI supports streaming response generation.
        # RESPONSE_LLM_PROVIDER is reserved for future providers.
        if response_provider and response_provider != 'openai':
            logger.warning(
                f"RESPONSE_LLM_PROVIDER={response_provider!r} is not supported "
                f"(only 'openai' available for response) — using OpenAI"
            )

        # --- Startup summary ---
        analysis_name = (
            f"Groq/{os.getenv('GROQ_ANALYSIS_MODEL', 'llama-3.3-70b-versatile')}"
            if self._analysis is not None
            else f"OpenAI/{os.getenv('OPENAI_AGENT_MODEL', 'gpt-4o-mini')}"
        )
        response_name = f"OpenAI/{os.getenv('OPENAI_AGENT_MODEL', 'gpt-4o-mini')}"
        embedding_name = f"OpenAI/{os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')}"
        logger.info(
            f"LLM routing — analysis: {analysis_name} | "
            f"response: {response_name} | "
            f"embeddings: {embedding_name}"
        )

    def _ensure_default(self) -> LLMInterface:
        if self._default is None:
            self._default = get_llm()
        return self._default

    def get_analysis_provider(self) -> AnalysisProvider:
        if self._analysis is not None:
            return self._analysis
        return self._ensure_default()

    def get_response_provider(self) -> ResponseProvider:
        if self._response is not None:
            return self._response
        return self._ensure_default()

    def get_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding is not None:
            return self._embedding
        return self._ensure_default()

    def get_default_llm(self) -> LLMInterface:
        """Backward-compatible: returns composite LLMInterface."""
        return self._ensure_default()

    def get_prompt_strategy(self) -> PromptStrategy:
        """Return the prompt strategy matching the current analysis provider."""
        if self._prompt_strategy is not None:
            return self._prompt_strategy
        return OpenAIPromptStrategy()

    # -- Manual overrides (used in tests or future multi-provider setup) --

    def set_analysis_provider(self, provider: AnalysisProvider) -> None:
        self._analysis = provider
        logger.info(f"Analysis provider overridden: {type(provider).__name__}")

    def set_response_provider(self, provider: ResponseProvider) -> None:
        self._response = provider
        logger.info(f"Response provider overridden: {type(provider).__name__}")

    def set_embedding_provider(self, provider: EmbeddingProvider) -> None:
        self._embedding = provider
        logger.info(f"Embedding provider overridden: {type(provider).__name__}")

    def set_prompt_strategy(self, strategy: PromptStrategy) -> None:
        self._prompt_strategy = strategy
        logger.info(f"Prompt strategy overridden: {type(strategy).__name__}")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_registry: Optional[LLMRegistry] = None


def get_llm_registry() -> LLMRegistry:
    global _registry
    if _registry is None:
        _registry = LLMRegistry()
    return _registry
