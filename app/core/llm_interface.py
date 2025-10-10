import os
from abc import ABC, abstractmethod
from typing import List, Optional


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


class OpenAILLM(LLMInterface):
    """Реализация для OpenAI"""

    def __init__(self, api_key: str):
        from langchain_openai import OpenAIEmbeddings, ChatOpenAI

        self.embeddings = OpenAIEmbeddings(
            model=os.getenv('EMBEDDING_MODEL', 'text-embedding-ada-002'),
            openai_api_key=api_key
        )
        self.chat_model = ChatOpenAI(
            model=self._get_agent_model(),
            openai_api_key=api_key,
            temperature=self._get_agent_temperature()
        )

    @staticmethod
    def _get_agent_model() -> str:
        return os.getenv('OPENAI_AGENT_MODEL', 'gpt-4o-mini')

    @staticmethod
    def _get_agent_temperature() -> float:
        try:
            return float(os.getenv('AGENT_TEMPERATURE', '0.7'))
        except ValueError:
            return 0.7
    
    def generate_embedding(self, text: str) -> List[float]:
        """Генерация эмбеддинга через OpenAI"""
        return self.embeddings.embed_query(text)
    
    def generate_response(self, prompt: str) -> str:
        """Генерация ответа через OpenAI"""
        response = self.chat_model.invoke(prompt)
        return response.content


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