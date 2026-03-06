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

logger = logging.getLogger(__name__)


class LLMRegistry:
    """Central registry that provides LLM instances by purpose.

    Default: all three capabilities are served by a single OpenAILLM
    (backward compatible with existing get_llm() behavior).

    When per-purpose env vars are set, returns specialized providers.
    """

    def __init__(self):
        self._default: Optional[LLMInterface] = None
        self._analysis: Optional[AnalysisProvider] = None
        self._response: Optional[ResponseProvider] = None
        self._embedding: Optional[EmbeddingProvider] = None

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


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_registry: Optional[LLMRegistry] = None


def get_llm_registry() -> LLMRegistry:
    global _registry
    if _registry is None:
        _registry = LLMRegistry()
    return _registry
