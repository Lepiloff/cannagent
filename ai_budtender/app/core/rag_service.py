from typing import List, Optional
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.schema import BaseRetriever, Document
from langchain_openai import ChatOpenAI
from app.core.llm_interface import get_llm
from app.db.repository import ProductRepository
from app.models.schemas import Product, ChatResponse
from app.config import settings


class ProductRetriever(BaseRetriever):
    """Кастомный ретривер для поиска товаров через pgvector"""
    
    def __init__(self, repository: ProductRepository):
        self.repository = repository
        self.llm = get_llm()
    
    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        """Поиск релевантных документов"""
        # Генерируем эмбеддинг для запроса
        query_embedding = self.llm.generate_embedding(query)
        
        # Ищем похожие товары
        similar_products = self.repository.search_similar_products(
            query_embedding, 
            limit=settings.search_limit
        )
        
        # Конвертируем в Document объекты для LangChain
        documents = []
        for product in similar_products:
            doc = Document(
                page_content=f"Товар: {product.name}\nОписание: {product.description}",
                metadata={"product_id": product.id, "name": product.name}
            )
            documents.append(doc)
        
        return documents
    
    async def aget_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        """Асинхронная версия поиска"""
        return self._get_relevant_documents(query, **kwargs)


class RAGService:
    """Сервис для RAG (Retrieval-Augmented Generation)"""
    
    def __init__(self, repository: ProductRepository):
        self.repository = repository
        self.retriever = ProductRetriever(repository)
        self.llm_interface = get_llm()
        
        # Create prompt template for AI Budtender
        self.prompt_template = PromptTemplate(
            input_variables=["query", "context", "history"],
            template="""
You are AI Budtender, an assistant for selecting cannabis products. 
Your task is to help users choose suitable products from our inventory.

Conversation history:
{history}

User query: {query}

Available products:
{context}

Provide personalized recommendations considering:
- Product effects and characteristics
- User preferences  
- Time of day (if mentioned)
- Usage experience

Response should be friendly, informative and helpful for selection.
If no suitable products are found, offer general recommendations.
"""
        )
    
    def process_query(self, query: str, history: Optional[List[str]] = None) -> ChatResponse:
        """Обработка запроса пользователя с помощью RAG"""
        
        # Получаем релевантные документы
        relevant_docs = self.retriever._get_relevant_documents(query)
        
        # Формируем контекст из найденных товаров
        context = "\n".join([doc.page_content for doc in relevant_docs])
        
        # Формируем историю
        history_text = "\n".join(history) if history else "Новый разговор"
        
        # Создаем финальный промпт
        prompt = self.prompt_template.format(
            query=query,
            context=context,
            history=history_text
        )
        
        # Получаем ответ от LLM
        response_text = self.llm_interface.generate_response(prompt)
        
        # Формируем список рекомендованных товаров
        recommended_products = []
        for doc in relevant_docs:
            product_id = doc.metadata.get("product_id")
            if product_id:
                product = self.repository.get_product(product_id)
                if product:
                    recommended_products.append(Product(
                        id=product.id,
                        name=product.name,
                        description=product.description,
                        created_at=product.created_at
                    ))
        
        return ChatResponse(
            response=response_text,
            recommended_products=recommended_products
        )
    
    def add_product_embeddings(self, product_id: int) -> bool:
        """Генерация и добавление эмбеддинга для товара"""
        product = self.repository.get_product(product_id)
        if not product:
            return False
        
        # Создаем текст для эмбеддинга
        text_for_embedding = f"{product.name} {product.description}"
        
        # Генерируем эмбеддинг
        embedding = self.llm_interface.generate_embedding(text_for_embedding)
        
        # Обновляем товар
        self.repository.update_product_embedding(product_id, embedding)
        
        return True 