from typing import List, Optional, Dict, Any, Tuple
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from app.core.llm_interface import get_llm
from app.core.intent_detection import IntentDetector, IntentType
from app.db.repository import StrainRepository
from app.models.schemas import Strain, ChatResponse, Feeling, HelpsWith, Negative, Flavor, Terpene
import os


class RAGService:
    """Enhanced RAG Service with intent detection and structured filtering"""
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
        self.llm_interface = get_llm()
        self.intent_detector = IntentDetector()
        
        # Simplified prompt template - let structured filtering do the heavy lifting
        self.prompt_template = PromptTemplate(
            input_variables=["query", "context", "history", "intent", "filters_applied"],
            template="""
You are AI Budtender, an expert cannabis consultant specializing in strain recommendations.

Conversation history:
{history}

User query: {query}
Detected intent: {intent}
Filters applied: {filters_applied}

Pre-selected suitable strains:
{context}

These strains have already been filtered based on your specific needs. 
Explain why each strain is a good match and provide helpful guidance for selection.
Focus on the specific benefits that align with the user's request.

Response should be friendly, informative and educational.
"""
        )
    
    def _get_relevant_strains(self, query: str) -> Tuple[List[Document], IntentType, Dict[str, Any]]:
        """Get relevant strains using intent-based structured filtering + vector search"""
        
        # Detect user intent
        detected_intent = self.intent_detector.detect_intent(query)
        filters = self.intent_detector.get_intent_filters(detected_intent)
        
        # Generate embedding for vector similarity (as secondary ranking)
        query_embedding = self.llm_interface.generate_embedding(query)
        
        # Use new smart search with intent filtering
        similar_strains = self.repository.search_strains_with_intent(
            query=query,
            query_embedding=query_embedding,
            limit=int(os.getenv('SEARCH_LIMIT', '5'))
        )
        
        # Convert to Document objects for LangChain with enriched content
        documents = []
        for strain in similar_strains:
            # Build rich context including effects and medical uses
            feelings = [f.name for f in strain.feelings] if strain.feelings else []
            helps_with = [h.name for h in strain.helps_with] if strain.helps_with else []
            negatives = [n.name for n in strain.negatives] if strain.negatives else []
            flavors = [f.name for f in strain.flavors] if strain.flavors else []
            
            content = f"""Strain: {strain.name}
Category: {strain.category or 'Unknown'}
THC: {strain.thc}% | CBD: {strain.cbd}%
Effects: {', '.join(feelings) if feelings else 'Not specified'}
Helps with: {', '.join(helps_with) if helps_with else 'Not specified'}
Flavors: {', '.join(flavors) if flavors else 'Not specified'}
Possible side effects: {', '.join(negatives) if negatives else 'Not specified'}
Description: {strain.description or strain.text_content or 'No description'}"""
            
            doc = Document(
                page_content=content,
                metadata={
                    "strain_id": strain.id,
                    "name": strain.name,
                    "slug": strain.slug,
                    "category": strain.category,
                    "feelings": feelings,
                    "helps_with": helps_with
                }
            )
            documents.append(doc)
        
        return documents, detected_intent, filters
    
    def _build_strain_url(self, strain_slug: str) -> Optional[str]:
        """Build full URL for strain"""
        if not strain_slug:
            return None
        base_url = os.getenv('CANNAMENTE_BASE_URL', 'http://localhost:8000')
        url_pattern = os.getenv('STRAIN_URL_PATTERN', '/strain/{slug}/')
        return f"{base_url}{url_pattern.format(slug=strain_slug)}"
    
    def process_query(self, query: str, history: Optional[List[str]] = None) -> ChatResponse:
        """Enhanced query processing with intent detection and structured filtering"""
        
        # Get relevant strains with intent detection
        relevant_strain_docs, detected_intent, applied_filters = self._get_relevant_strains(query)
        
        # Form context from found strains
        context = "\n\n".join([doc.page_content for doc in relevant_strain_docs])
        
        # Form history
        history_text = "\n".join(history) if history else "New conversation"
        
        # Prepare filter summary for AI explanation
        filters_summary = f"Intent: {detected_intent.value if detected_intent != IntentType.GENERAL else 'general inquiry'}"
        if applied_filters.get('required_feelings'):
            filters_summary += f", Required effects: {', '.join(applied_filters['required_feelings'])}"
        if applied_filters.get('preferred_categories'):
            filters_summary += f", Preferred types: {', '.join(applied_filters['preferred_categories'])}"
        if applied_filters.get('exclude_feelings'):
            filters_summary += f", Avoiding effects: {', '.join(applied_filters['exclude_feelings'])}"
        
        # Create final prompt
        prompt = self.prompt_template.format(
            query=query,
            context=context,
            history=history_text,
            intent=detected_intent.value,
            filters_applied=filters_summary
        )
        
        # Get response from LLM
        response_text = self.llm_interface.generate_response(prompt)
        
        # Build recommended strains list with full relations
        recommended_strains = []
        for doc in relevant_strain_docs:
            strain_id = doc.metadata.get("strain_id")
            
            if strain_id:
                strain = self.repository.get_strain_with_relations(strain_id)
                if strain:
                    strain_schema = Strain(
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
                        updated_at=strain.updated_at,
                        feelings=[Feeling(id=f.id, name=f.name, energy_type=f.energy_type, created_at=f.created_at) for f in strain.feelings],
                        helps_with=[HelpsWith(id=h.id, name=h.name, created_at=h.created_at) for h in strain.helps_with],
                        negatives=[Negative(id=n.id, name=n.name, created_at=n.created_at) for n in strain.negatives],
                        flavors=[Flavor(id=fl.id, name=fl.name, created_at=fl.created_at) for fl in strain.flavors],
                        terpenes=[Terpene(id=t.id, name=t.name, description=t.description, created_at=t.created_at) for t in strain.terpenes]
                    )
                    recommended_strains.append(strain_schema)
        
        return ChatResponse(
            response=response_text,
            recommended_strains=recommended_strains,
            detected_intent=detected_intent.value,
            filters_applied=applied_filters
        )
    
    def add_strain_embeddings(self, strain_id: int) -> bool:
        """Generate and add embedding for strain with structured data"""
        strain = self.repository.get_strain_with_relations(strain_id)
        if not strain:
            return False
        
        # Create rich text for embedding including structured effects data
        text_parts = [strain.name]
        if strain.title:
            text_parts.append(strain.title)
        if strain.description:
            text_parts.append(strain.description)
        if strain.text_content:
            text_parts.append(strain.text_content)
        if strain.category:
            text_parts.append(f"Category: {strain.category}")
        
        # Add cannabinoid content
        if strain.thc:
            text_parts.append(f"THC: {strain.thc}%")
        if strain.cbd:
            text_parts.append(f"CBD: {strain.cbd}%")
        
        # Add effects and medical uses (MOST IMPORTANT for search)
        if strain.feelings:
            feelings = [f.name for f in strain.feelings]
            text_parts.append(f"Effects: {', '.join(feelings)}")
        
        if strain.helps_with:
            conditions = [h.name for h in strain.helps_with]
            text_parts.append(f"Helps with: {', '.join(conditions)}")
        
        if strain.flavors:
            flavors = [f.name for f in strain.flavors]
            text_parts.append(f"Flavors: {', '.join(flavors)}")
        
        text_for_embedding = " ".join(text_parts)
        
        # Generate embedding
        embedding = self.llm_interface.generate_embedding(text_for_embedding)
        
        # Update strain
        self.repository.update_strain_embedding(strain_id, embedding)
        
        return True
    
    def analyze_query_intent(self, query: str) -> Dict[str, Any]:
        """Analyze query and return intent detection results for debugging"""
        intent = self.intent_detector.detect_intent(query)
        filters = self.intent_detector.get_intent_filters(intent)
        
        return {
            "query": query,
            "detected_intent": intent.value,
            "applied_filters": filters,
            "explanation": f"Query '{query}' was categorized as '{intent.value}' intent"
        }