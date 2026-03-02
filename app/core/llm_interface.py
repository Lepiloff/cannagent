import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

logger = logging.getLogger(__name__)


class LLMInterface(ABC):
    """Абстрактный интерфейс для LLM провайдеров"""

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """Генерация эмбеддинга для текста"""
        pass

    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        """Генерация ответа на промпт"""
        pass

    def generate_response_with_system(self, system_prompt: str, user_prompt: str) -> str:
        """Генерация ответа с раздельными system/user промптами для prompt caching.
        По умолчанию объединяет в один промпт (для MockLLM)."""
        return self.generate_response(f"{system_prompt}\n\n{user_prompt}")

    async def agenerate_embedding(self, text: str) -> List[float]:
        """Async генерация эмбеддинга. По умолчанию делегирует sync-версии через thread pool."""
        return await asyncio.to_thread(self.generate_embedding, text)

    async def agenerate_response(self, prompt: str) -> str:
        """Async генерация ответа. По умолчанию делегирует sync-версии через thread pool."""
        return await asyncio.to_thread(self.generate_response, prompt)

    async def agenerate_response_with_system(self, system_prompt: str, user_prompt: str) -> str:
        """Async генерация с раздельными system/user промптами для prompt caching.
        По умолчанию делегирует sync-версии."""
        return await asyncio.to_thread(self.generate_response_with_system, system_prompt, user_prompt)

    def generate_structured_response(self, system_prompt: str, user_prompt: str, output_schema: type):
        """Structured output generation. Returns Pydantic model or raw string (fallback).
        Default: delegates to text generation (for MockLLM)."""
        return self.generate_response_with_system(system_prompt, user_prompt)

    async def agenerate_structured_response(self, system_prompt: str, user_prompt: str, output_schema: type):
        """Async structured output generation. Returns Pydantic model or raw string (fallback).
        Default: delegates to text generation (for MockLLM)."""
        return await self.agenerate_response_with_system(system_prompt, user_prompt)

    async def astream_response(self, prompt: str) -> AsyncIterator[str]:
        """Async streaming генерация — yields chunks текста.
        По умолчанию возвращает полный ответ одним chunk."""
        result = await self.agenerate_response(prompt)
        yield result


class OpenAILLM(LLMInterface):
    """Реализация для OpenAI"""

    def __init__(self, api_key: str):
        from langchain_openai import OpenAIEmbeddings, ChatOpenAI

        self.embeddings = OpenAIEmbeddings(
            model=os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small'),
            openai_api_key=api_key
        )
        self.chat_model = ChatOpenAI(
            model=self._get_agent_model(),
            openai_api_key=api_key,
            temperature=self._get_agent_temperature()
        )
        self.analysis_model = ChatOpenAI(
            model=self._get_agent_model(),
            openai_api_key=api_key,
            temperature=self._get_analysis_temperature()
        )
        self._structured_cache = {}  # schema_class -> structured_model

    @staticmethod
    def _get_agent_model() -> str:
        return os.getenv('OPENAI_AGENT_MODEL', 'gpt-4o-mini')

    @staticmethod
    def _get_agent_temperature() -> float:
        try:
            return float(os.getenv('AGENT_TEMPERATURE', '0.7'))
        except ValueError:
            return 0.7

    @staticmethod
    def _get_analysis_temperature() -> float:
        try:
            return float(os.getenv('ANALYSIS_TEMPERATURE', '0.2'))
        except ValueError:
            return 0.2

    def generate_embedding(self, text: str) -> List[float]:
        """Генерация эмбеддинга через OpenAI"""
        return self.embeddings.embed_query(text)

    def generate_response(self, prompt: str) -> str:
        """Генерация ответа через OpenAI"""
        response = self.chat_model.invoke(prompt)
        return response.content

    def generate_response_with_system(self, system_prompt: str, user_prompt: str) -> str:
        """Генерация ответа с раздельными system/user messages для OpenAI prompt caching.

        OpenAI автоматически кеширует prefix промпта (>1024 tokens).
        System message содержит статический контент (инструкции + taxonomy) — кешируется.
        User message содержит переменный контент (запрос, сессия) — не кешируется.
        Результат: до 50% экономии токенов и до 80% снижение латентности на cached portion.
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.analysis_model.invoke(messages)
        self._log_cache_stats(response)
        return response.content

    async def agenerate_embedding(self, text: str) -> List[float]:
        """Async генерация эмбеддинга через LangChain ainvoke"""
        return await self.embeddings.aembed_query(text)

    async def agenerate_response(self, prompt: str) -> str:
        """Async генерация ответа через LangChain ainvoke"""
        response = await self.chat_model.ainvoke(prompt)
        return response.content

    async def agenerate_response_with_system(self, system_prompt: str, user_prompt: str) -> str:
        """Async версия generate_response_with_system для prompt caching."""
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await self.analysis_model.ainvoke(messages)
        self._log_cache_stats(response)
        return response.content

    def _get_structured_model(self, output_schema: type):
        """Get or create cached structured output model."""
        if output_schema not in self._structured_cache:
            self._structured_cache[output_schema] = self.analysis_model.with_structured_output(output_schema)
        return self._structured_cache[output_schema]

    def _log_cache_stats(self, response) -> None:
        """Log prompt cache statistics from response metadata."""
        if hasattr(response, 'response_metadata'):
            token_usage = response.response_metadata.get('token_usage', {})
            prompt_details = token_usage.get('prompt_tokens_details', {})
            cached = prompt_details.get('cached_tokens', 0)
            total_prompt = token_usage.get('prompt_tokens', 0)
            if cached > 0:
                logger.info(f"Prompt cache hit: {cached}/{total_prompt} tokens cached ({cached/total_prompt*100:.0f}%)")
            elif total_prompt > 0:
                logger.debug(f"Prompt cache miss: 0/{total_prompt} tokens cached")

    def generate_structured_response(self, system_prompt: str, user_prompt: str, output_schema: type):
        """Structured output via OpenAI JSON schema — returns validated Pydantic model."""
        from langchain_core.messages import SystemMessage, HumanMessage

        structured_model = self._get_structured_model(output_schema)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return structured_model.invoke(messages)

    async def agenerate_structured_response(self, system_prompt: str, user_prompt: str, output_schema: type):
        """Async structured output via OpenAI JSON schema — returns validated Pydantic model."""
        from langchain_core.messages import SystemMessage, HumanMessage

        structured_model = self._get_structured_model(output_schema)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return await structured_model.ainvoke(messages)

    async def astream_response(self, prompt: str) -> AsyncIterator[str]:
        """Async streaming генерация через LangChain astream."""
        async for chunk in self.chat_model.astream(prompt):
            if chunk.content:
                yield chunk.content


class MockLLM(LLMInterface):
    """Мок для тестирования без OpenAI"""
    
    def generate_embedding(self, text: str) -> List[float]:
        """Генерация фиктивного эмбеддинга"""
        import hashlib
        import random
        
        # Создаем детерминированный эмбеддинг на основе хеша текста
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest(), 16) % (2**32)
        
        random.seed(seed)
        return [random.uniform(-1, 1) for _ in range(int(os.getenv('VECTOR_DIMENSION', '1536')))]
    
    def generate_response(self, prompt: str) -> str:
        """Генерация мок-ответа"""
        return (
            "Это мок-ответ от AI Budtender. "
            "Для полноценной работы настройте OPENAI_API_KEY в переменных окружения. "
            "Рекомендую попробовать товары из нашего ассортимента!"
        )


def get_llm() -> LLMInterface:
    """Фабрика для создания LLM провайдера"""
    mock_mode = os.getenv('MOCK_MODE', 'false').lower() == 'true'
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    if mock_mode or not openai_api_key:
        return MockLLM()
    else:
        return OpenAILLM(openai_api_key) 