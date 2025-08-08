from typing import List, Optional
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.schema import Document
from langchain_openai import ChatOpenAI
from app.core.llm_interface import get_llm
from app.db.repository import StrainRepository
from app.models.schemas import Strain, ChatResponse
from app.config import settings


class RAGService:
    """Сервис для RAG (Retrieval-Augmented Generation)"""
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
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
    

    
    def _get_relevant_strains(self, query: str) -> List[Document]:
        """Поиск релевантных штаммов"""
        # Генерируем эмбеддинг для запроса
        query_embedding = self.llm_interface.generate_embedding(query)
        
        # Ищем похожие штаммы
        similar_strains = self.repository.search_similar_strains(
            query_embedding, 
            limit=settings.search_limit
        )
        
        # Конвертируем в Document объекты для LangChain
        documents = []
        for strain in similar_strains:
            content = f"""Strain: {strain.name}
Category: {strain.category or 'Unknown'}
THC: {strain.thc}% | CBD: {strain.cbd}%
Description: {strain.description or strain.text_content or 'No description'}
Rating: {strain.rating or 'Not rated'}"""
            
            doc = Document(
                page_content=content,
                metadata={
                    "strain_id": strain.id, 
                    "name": strain.name,
                    "slug": strain.slug,
                    "category": strain.category
                }
            )
            documents.append(doc)
        
        return documents
    
    def _build_strain_url(self, strain_slug: str) -> Optional[str]:
        """Формирует полный URL для штамма"""
        if not strain_slug:
            return None
        return f"{settings.cannamente_base_url}{settings.strain_url_pattern.format(slug=strain_slug)}"
    
    def process_query(self, query: str, history: Optional[List[str]] = None) -> ChatResponse:
        """Обработка запроса пользователя с помощью RAG"""
        
        # Получаем релевантные штаммы (основной источник данных)
        relevant_strain_docs = self._get_relevant_strains(query)
        
        # Формируем контекст из найденных штаммов
        context = "\n".join([doc.page_content for doc in relevant_strain_docs])
        
        # Формируем историю
        history_text = "\n".join(history) if history else "Новый разговор"
        
        # Обновляем промпт для работы со штаммами
        strain_prompt_template = PromptTemplate(
            input_variables=["query", "context", "history"],
            template="""
You are AI Budtender, an expert cannabis consultant specializing in strain recommendations.
Your task is to help users choose suitable cannabis strains based on their needs and preferences.

Conversation history:
{history}

User query: {query}

Available strains:
{context}

Provide personalized strain recommendations considering:
- Strain effects (Indica/Sativa/Hybrid characteristics)
- Cannabinoid content (THC, CBD, CBG levels)
- User preferences and desired effects
- Time of day (if mentioned)
- User experience level
- Medical vs recreational use

Response should be friendly, informative and helpful for strain selection.
Focus on explaining why each strain matches the user's needs.
If no perfect match is found, suggest the closest alternatives.
"""
        )
        
        # Создаем финальный промпт
        prompt = strain_prompt_template.format(
            query=query,
            context=context,
            history=history_text
        )
        
        # Получаем ответ от LLM
        response_text = self.llm_interface.generate_response(prompt)
        
        # Формируем список рекомендованных штаммов
        recommended_strains = []
        for doc in relevant_strain_docs:
            strain_id = doc.metadata.get("strain_id")
            strain_slug = doc.metadata.get("slug")
            
            if strain_id:
                strain = self.repository.get_strain(strain_id)
                if strain:
                    recommended_strains.append(Strain(
                        id=strain.id,
                        name=strain.name,
                        title=strain.title,
                        description=strain.description,
                        text_content=strain.text_content,
                        keywords=strain.keywords,
                        cbd=strain.cbd,
                        thc=strain.thc,
                        cbg=strain.cbg,
                        rating=strain.rating,
                        category=strain.category,
                        img=strain.img,
                        img_alt_text=strain.img_alt_text,
                        active=strain.active,
                        top=strain.top,
                        main=strain.main,
                        is_review=strain.is_review,
                        slug=strain.slug,
                        url=self._build_strain_url(strain.slug),
                        created_at=strain.created_at,
                        updated_at=strain.updated_at
                    ))
        
        return ChatResponse(
            response=response_text,
            recommended_strains=recommended_strains,

        )
    

    
    def add_strain_embeddings(self, strain_id: int) -> bool:
        """Генерация и добавление эмбеддинга для штамма"""
        strain = self.repository.get_strain(strain_id)
        if not strain:
            return False
        
        # Создаем текст для эмбеддинга из всех доступных полей
        text_parts = [strain.name]
        if strain.title:
            text_parts.append(strain.title)
        if strain.description:
            text_parts.append(strain.description)
        if strain.text_content:
            text_parts.append(strain.text_content)
        if strain.category:
            text_parts.append(f"Category: {strain.category}")
        if strain.thc:
            text_parts.append(f"THC: {strain.thc}%")
        if strain.cbd:
            text_parts.append(f"CBD: {strain.cbd}%")
        
        text_for_embedding = " ".join(text_parts)
        
        # Генерируем эмбеддинг
        embedding = self.llm_interface.generate_embedding(text_for_embedding)
        
        # Обновляем штамм
        self.repository.update_strain_embedding(strain_id, embedding)
        
        return True 